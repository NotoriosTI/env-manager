"""Integración real contra Google Secret Manager (blueprint §1.1).

Crea un secreto JSON consolidado de mentira en el proyecto, comprueba que
env-manager lo lee y que, una vez leído, cada valor se comporta igual que
cualquier secreto individual: mismo tipado, misma escritura a ``os.environ``,
misma resolución por `get` / `require`, y convivencia con secretos que sí viven
sueltos en GSM.

No corre por defecto. Necesita credenciales reales:

    RUN_REAL_GCP_TESTS=1 ENV_MANAGER_ITEST_PROJECT=my-test-project \
      pytest -m integration tests/test_consolidated_secret_gsm_integration.py

Los secretos que crea llevan prefijo ``env-manager-itest-`` y se borran en el
teardown, pasen o fallen los tests.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

import env_manager.manager as manager_module
from conftest import write_config
from env_manager import ConfigManager
from env_manager.cli.secrets import set_key
from env_manager.loaders import GCPSecretLoader

#: Contenido del secreto consolidado. Todo inventado: ningún valor real.
CONSOLIDATED_PAYLOAD = {
    "ITEST_STR": "hello-from-consolidated",
    "ITEST_INT": "4242",
    "ITEST_BOOL": "true",
    "ITEST_NESTED": {"a": 1, "b": [2, 3]},
}

#: Secreto suelto, del formato de siempre: una clave, un secreto, un valor.
INDIVIDUAL_VALUE = "hello-from-individual"


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def gcp_project_id() -> str:
    """Require an explicit opt-in and project before constructing a GCP client."""

    if os.getenv("RUN_REAL_GCP_TESTS") != "1":
        pytest.skip("Set RUN_REAL_GCP_TESTS=1 to run GCP integration tests.")
    project_id = os.getenv("ENV_MANAGER_ITEST_PROJECT", "").strip()
    if not project_id:
        pytest.skip(
            "Set non-empty ENV_MANAGER_ITEST_PROJECT explicitly before running "
            "GCP integration tests."
        )
    return project_id


@pytest.fixture(scope="module")
def gsm_secrets(gcp_project_id):
    """Create the throwaway secrets in GSM and remove them afterwards."""

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{gcp_project_id}"
    suffix = uuid.uuid4().hex[:8]

    consolidated_name = f"env-manager-itest-{suffix}-config"
    individual_name = f"env-manager-itest-{suffix}-ITEST_INDIVIDUAL"
    created: list[str] = []

    def create(secret_id: str, payload: str) -> None:
        client.create_secret(
            parent=parent,
            secret_id=secret_id,
            secret={"replication": {"automatic": {}}},
        )
        created.append(f"{parent}/secrets/{secret_id}")
        client.add_secret_version(
            parent=f"{parent}/secrets/{secret_id}",
            payload={"data": payload.encode("utf-8")},
        )

    try:
        create(consolidated_name, json.dumps(CONSOLIDATED_PAYLOAD))
        create(individual_name, INDIVIDUAL_VALUE)
        yield {
            "consolidated": consolidated_name,
            "individual": individual_name,
            "client": client,
            "project_id": gcp_project_id,
        }
    finally:
        # El teardown no se salta ni aunque los tests fallen: un secreto huérfano
        # se sigue facturando por versión habilitada (§1.1).
        for name in created:
            try:
                client.delete_secret(name=name)
            except Exception as exc:  # noqa: BLE001 - se reporta, no se traga
                pytest.fail(
                    f"No se pudo borrar el secreto de prueba {name}: {exc}. "
                    "Bórralo a mano, sigue facturándose."
                )


@pytest.fixture
def config_path(tmp_path, gsm_secrets):
    """YAML that mixes consolidated keys with one genuinely individual secret."""

    return write_config(
        tmp_path,
        f"""\
        environments:
          production:
            origin: gcp
            gcp_project_id: {gsm_secrets["project_id"]}
            consolidated_secret: {gsm_secrets["consolidated"]}
            default: true

        variables:
          ITEST_STR:
            source: ITEST_STR
            type: str
          ITEST_INT:
            source: ITEST_INT
            type: int
          ITEST_BOOL:
            source: ITEST_BOOL
            type: bool
          ITEST_NESTED:
            source: ITEST_NESTED
            type: str
          ITEST_INDIVIDUAL:
            source: {gsm_secrets["individual"]}
            type: str
          ITEST_WITH_DEFAULT:
            source: ITEST_NOT_ANYWHERE
            type: int
            default: 7
        """,
    )


@pytest.fixture
def manager(config_path):
    manager_module._SINGLETON = None
    cm = ConfigManager(str(config_path), auto_load=True)
    yield cm
    manager_module._SINGLETON = None
    for key in (
        "ITEST_STR",
        "ITEST_INT",
        "ITEST_BOOL",
        "ITEST_NESTED",
        "ITEST_INDIVIDUAL",
        "ITEST_WITH_DEFAULT",
    ):
        os.environ.pop(key, None)


class TestReadsTheConsolidatedSecret:
    def test_string_value_arrives_intact(self, manager):
        assert manager.get("ITEST_STR") == "hello-from-consolidated"

    def test_declared_types_are_coerced(self, manager):
        assert manager.get("ITEST_INT") == 4242
        assert manager.get("ITEST_BOOL") is True

    def test_non_string_json_values_arrive_serialised(self, manager):
        # El payload trae un objeto anidado; el contrato dice que llega como JSON.
        assert json.loads(manager.get("ITEST_NESTED")) == {"a": 1, "b": [2, 3]}

    def test_one_api_call_serves_every_consolidated_key(self, gsm_secrets):
        loader = GCPSecretLoader(
            gsm_secrets["project_id"],
            consolidated_secret=gsm_secrets["consolidated"],
        )
        real_access = loader._client.access_secret_version
        calls: list[str] = []

        def counting_access(name, **kwargs):
            calls.append(name)
            return real_access(name=name, **kwargs)

        loader._client.access_secret_version = counting_access

        assert loader.get("ITEST_STR") == "hello-from-consolidated"
        assert loader.get("ITEST_INT") == "4242"
        assert loader.get("ITEST_BOOL") == "true"

        # Tres claves, un solo viaje a GSM: el del secreto consolidado.
        assert len(calls) == 1
        assert gsm_secrets["consolidated"] in calls[0]


class TestBehavesLikeAnyOtherSecret:
    """Una vez leído, un valor consolidado no se distingue de uno individual."""

    def test_consolidated_and_individual_resolve_side_by_side(self, manager):
        assert manager.get("ITEST_STR") == "hello-from-consolidated"
        assert manager.get("ITEST_INDIVIDUAL") == "hello-from-individual"

    def test_both_land_in_os_environ(self, manager):
        assert os.environ["ITEST_STR"] == "hello-from-consolidated"
        assert os.environ["ITEST_INDIVIDUAL"] == "hello-from-individual"

    def test_require_works_for_both(self, manager):
        assert manager.require("ITEST_STR") == "hello-from-consolidated"
        assert manager.require("ITEST_INDIVIDUAL") == "hello-from-individual"

    def test_values_property_exposes_both(self, manager):
        values = manager.values
        assert values["ITEST_STR"] == "hello-from-consolidated"
        assert values["ITEST_INDIVIDUAL"] == "hello-from-individual"

    def test_a_key_missing_everywhere_falls_back_to_its_default(self, manager):
        # No está en el JSON consolidado ni existe como secreto suelto.
        assert manager.get("ITEST_WITH_DEFAULT") == 7

    def test_unknown_key_behaves_like_always(self, manager):
        assert manager.get("ITEST_NOT_DECLARED") is None
        assert manager.get("ITEST_NOT_DECLARED", "fallback") == "fallback"


class TestLoaderLevelBehaviour:
    def test_key_absent_from_payload_falls_back_to_an_individual_lookup(
        self, gsm_secrets
    ):
        loader = GCPSecretLoader(
            gsm_secrets["project_id"],
            consolidated_secret=gsm_secrets["consolidated"],
        )
        # Vive fuera del JSON, como secreto suelto: se resuelve igual.
        assert loader.get(gsm_secrets["individual"]) == "hello-from-individual"

    def test_a_secret_that_does_not_exist_is_none_not_an_error(self, gsm_secrets):
        loader = GCPSecretLoader(
            gsm_secrets["project_id"],
            consolidated_secret=gsm_secrets["consolidated"],
        )
        assert loader.get(f"env-manager-itest-{uuid.uuid4().hex}") is None

    def test_get_many_mixes_both_sources(self, gsm_secrets):
        loader = GCPSecretLoader(
            gsm_secrets["project_id"],
            consolidated_secret=gsm_secrets["consolidated"],
        )
        result = loader.get_many(["ITEST_STR", gsm_secrets["individual"]])
        assert result == {
            "ITEST_STR": "hello-from-consolidated",
            gsm_secrets["individual"]: "hello-from-individual",
        }


def test_rotation_from_versionless_resource_destroys_disabled_versions(
    gcp_project_id,
):
    """Exercise first-write and billable-version cleanup on a throwaway secret."""

    from google.api_core import exceptions as gcp_exceptions
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    project_path = f"projects/{gcp_project_id}"
    secret_id = f"env-manager-itest-rotation-{uuid.uuid4().hex[:8]}"
    secret_path = f"{project_path}/secrets/{secret_id}"

    try:
        client.create_secret(
            parent=project_path,
            secret_id=secret_id,
            secret={"replication": {"automatic": {}}},
        )
        first = set_key(gcp_project_id, secret_id, "A", "1", client=client)
        assert first["created_version"] is not None
        assert first["destroyed_versions"] == []

        enabled_old = client.add_secret_version(
            parent=secret_path,
            payload={"data": json.dumps({"A": "1"}).encode("utf-8")},
        )
        client.disable_secret_version(name=first["created_version"])

        rotated = set_key(gcp_project_id, secret_id, "B", "2", client=client)

        assert first["created_version"] in rotated["destroyed_versions"]
        assert enabled_old.name in rotated["destroyed_versions"]
        prior_disabled = client.get_secret_version(name=first["created_version"])
        assert prior_disabled.state.name == "DESTROYED"

        billable = [
            version.name
            for version in client.list_secret_versions(parent=secret_path)
            if version.state.name in {"ENABLED", "DISABLED"}
        ]
        assert billable == [rotated["created_version"]]
    finally:
        try:
            client.delete_secret(name=secret_path)
        except gcp_exceptions.NotFound:
            pass
        except Exception as exc:  # noqa: BLE001 - cleanup failure must be visible
            pytest.fail(
                f"Could not delete disposable rotation secret {secret_path}: {exc}. "
                "Delete it manually because its versions remain billable."
            )
