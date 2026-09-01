"""Rotación del secreto consolidado con destrucción de la versión anterior.

Blueprint §1.1: guardar una actualización no puede dejar versiones viejas
habilitadas. Espejo de tests/secrets-rotation.test.ts en el repo JS.
"""

import json
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as gcp_exceptions

from env_manager.cli.secrets import (
    SecretDestroyError,
    SecretsError,
    list_keys,
    read_value_from_stdin,
    set_key,
)

PROJECT = "proj"
SECRET = "app-config"


class FakeClient:
    """Cliente de GSM en memoria: versiones numeradas y estado por versión."""

    def __init__(self, payload="{}", *, versions=("1",), missing=False):
        self.missing = missing
        self.payloads = {v: payload for v in versions}
        self.states = {v: "ENABLED" for v in versions}
        self.destroy_error = None
        self.added = []
        self.destroyed = []

    # -- lectura -------------------------------------------------------------
    def _version_id(self, name):
        return name.rsplit("/", 1)[-1]

    def access_secret_version(self, name):
        if self.missing:
            raise gcp_exceptions.NotFound("no such secret")
        version = self._version_id(name)
        if version == "latest":
            version = max(self.payloads, key=int)
        return SimpleNamespace(
            payload=SimpleNamespace(data=self.payloads[version].encode("utf-8"))
        )

    def list_secret_versions(self, parent):
        return [
            SimpleNamespace(
                name=f"{parent}/versions/{v}",
                state=SimpleNamespace(name=self.states[v]),
            )
            for v in sorted(self.payloads, key=int, reverse=True)
        ]

    # -- escritura -----------------------------------------------------------
    def add_secret_version(self, parent, payload):
        new_id = str(max((int(v) for v in self.payloads), default=0) + 1)
        self.payloads[new_id] = payload["data"].decode("utf-8")
        self.states[new_id] = "ENABLED"
        name = f"{parent}/versions/{new_id}"
        self.added.append(name)
        return SimpleNamespace(name=name)

    def destroy_secret_version(self, name):
        if self.destroy_error is not None:
            raise self.destroy_error
        self.states[self._version_id(name)] = "DESTROYED"
        self.destroyed.append(name)
        return SimpleNamespace(name=name)


class TestSetKey:
    def test_creates_new_version_and_destroys_the_old_one(self):
        client = FakeClient(json.dumps({"A": "1"}), versions=("1",))

        result = set_key(PROJECT, SECRET, "B", "2", client=client)

        assert result["unchanged"] is False
        assert result["created_version"].endswith("/versions/2")
        assert result["destroyed_versions"] == [
            f"projects/{PROJECT}/secrets/{SECRET}/versions/1"
        ]
        assert client.states["1"] == "DESTROYED"
        assert client.states["2"] == "ENABLED"

    def test_merges_instead_of_replacing_the_payload(self):
        client = FakeClient(json.dumps({"A": "1"}), versions=("1",))

        set_key(PROJECT, SECRET, "B", "2", client=client)

        assert json.loads(client.payloads["2"]) == {"A": "1", "B": "2"}

    def test_writing_the_same_value_creates_no_version(self):
        client = FakeClient(json.dumps({"A": "1"}), versions=("1",))

        result = set_key(PROJECT, SECRET, "A", "1", client=client)

        assert result["unchanged"] is True
        assert result["created_version"] is None
        assert client.added == []
        assert client.destroyed == []

    def test_destroys_every_previously_enabled_version(self):
        client = FakeClient(json.dumps({"A": "1"}), versions=("1", "2", "3"))

        result = set_key(PROJECT, SECRET, "B", "2", client=client)

        assert len(result["destroyed_versions"]) == 3
        assert [v for v, s in client.states.items() if s == "ENABLED"] == ["4"]

    def test_a_failed_destroy_names_the_dangling_version(self):
        client = FakeClient(json.dumps({"A": "1"}), versions=("1",))
        client.destroy_error = gcp_exceptions.PermissionDenied("nope")

        with pytest.raises(SecretDestroyError, match="still billable"):
            set_key(PROJECT, SECRET, "B", "2", client=client)

        # La versión nueva quedó viva: la app nunca se queda sin secreto.
        assert client.states["2"] == "ENABLED"

    def test_missing_secret_is_an_error_not_a_creation(self):
        client = FakeClient(missing=True)

        with pytest.raises(SecretsError, match="does not create secrets"):
            set_key(PROJECT, SECRET, "A", "1", client=client)

        assert client.added == []

    def test_refuses_to_overwrite_a_non_json_payload(self):
        client = FakeClient("no soy json", versions=("1",))

        with pytest.raises(SecretsError, match="valid JSON"):
            set_key(PROJECT, SECRET, "A", "1", client=client)

        assert client.added == []

    def test_refuses_to_overwrite_a_non_object_payload(self):
        client = FakeClient("[1, 2, 3]", versions=("1",))

        with pytest.raises(SecretsError, match="must contain a JSON object"):
            set_key(PROJECT, SECRET, "A", "1", client=client)

    def test_empty_payload_is_treated_as_an_empty_object(self):
        client = FakeClient("", versions=("1",))

        set_key(PROJECT, SECRET, "A", "1", client=client)

        assert json.loads(client.payloads["2"]) == {"A": "1"}

    def test_requires_a_key_name(self):
        client = FakeClient(json.dumps({}), versions=("1",))

        with pytest.raises(SecretsError, match="key name is required"):
            set_key(PROJECT, SECRET, "", "1", client=client)


class TestListKeys:
    def test_returns_key_names_sorted(self):
        client = FakeClient(json.dumps({"B": "2", "A": "1"}), versions=("1",))

        assert list_keys(PROJECT, SECRET, client=client) == ["A", "B"]

    def test_never_returns_values(self):
        client = FakeClient(json.dumps({"A": "super-secret"}), versions=("1",))

        assert "super-secret" not in list_keys(PROJECT, SECRET, client=client)


class TestStdin:
    def test_reads_the_value_and_strips_one_trailing_newline(self):
        assert read_value_from_stdin(["hola\n"]) == "hola"

    def test_keeps_inner_newlines(self):
        assert read_value_from_stdin(["a\n", "b\n"]) == "a\nb"

    def test_empty_stdin_is_an_error(self):
        with pytest.raises(SecretsError, match="No value provided"):
            read_value_from_stdin([])
