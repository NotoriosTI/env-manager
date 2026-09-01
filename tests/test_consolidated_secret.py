"""Tests for consolidated-secret support (one JSON secret per app)."""

import json

import pytest
from google.api_core import exceptions as gcp_exceptions

from env_manager.environment import parse_environments
from env_manager.loaders import GCPSecretLoader
from env_manager.manager import ConfigManager


def _mock_gcp_client(mocker, secrets: dict[str, str], module: str = "env_manager.loaders.gcp"):
    """Mock the Secret Manager client to serve from a name→payload dict."""
    client_mock = mocker.Mock()

    def access(name):
        # name = projects/<proj>/secrets/<secret>/versions/latest
        secret_name = name.split("/secrets/")[1].split("/")[0]
        if secret_name not in secrets:
            raise gcp_exceptions.NotFound(f"missing {secret_name}")
        response = mocker.Mock()
        response.payload.data = secrets[secret_name].encode("utf-8")
        return response

    # El loader pasa timeout y retry en cada llamada (§1.5.3); el mock los
    # acepta y los ignora.
    client_mock.access_secret_version.side_effect = (
        lambda name, timeout=None, retry=None: access(name)
    )
    mocker.patch(
        f"{module}.secretmanager.SecretManagerServiceClient",
        return_value=client_mock,
    )
    return client_mock


def test_loader_preloads_from_consolidated_json(mocker):
    client = _mock_gcp_client(
        mocker,
        {"app-config": json.dumps({"DB_USER": "svc", "DB_PORT": 5432})},
    )

    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    assert loader.get("DB_USER") == "svc"
    assert loader.get("DB_PORT") == "5432"  # non-str values serialised
    # A single API call: the consolidated secret itself
    client.access_secret_version.assert_called_once()


def test_loader_falls_back_to_individual_for_missing_keys(mocker):
    client = _mock_gcp_client(
        mocker,
        {
            "app-config": json.dumps({"DB_USER": "svc"}),
            "EXTRA_KEY": "individual-value",
        },
    )

    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    assert loader.get("EXTRA_KEY") == "individual-value"
    assert loader.get("DB_USER") == "svc"
    # consolidated + 1 individual fetch
    assert client.access_secret_version.call_count == 2


def test_loader_ignores_invalid_consolidated_payloads(mocker, caplog):
    import logging

    client = _mock_gcp_client(
        mocker,
        {"app-config": "not json {", "DB_USER": "svc"},
    )

    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        assert loader.get("DB_USER") == "svc"
    assert "not valid" in caplog.text.replace("\n", " ")


def test_loader_ignores_non_object_consolidated_payloads(mocker):
    _mock_gcp_client(
        mocker,
        {"app-config": json.dumps(["a", "b"]), "DB_USER": "svc"},
    )

    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    assert loader.get("DB_USER") == "svc"


def test_loader_missing_consolidated_secret_falls_back(mocker):
    _mock_gcp_client(mocker, {"DB_USER": "svc"})

    loader = GCPSecretLoader(project_id="p", consolidated_secret="does-not-exist")

    assert loader.get("DB_USER") == "svc"


def test_parse_environments_accepts_consolidated_secret():
    envs = parse_environments(
        {
            "environments": {
                "production": {
                    "origin": "gcp",
                    "gcp_project_id": "notorios",
                    "consolidated_secret": "app-config",
                },
                "local": {"origin": "local", "default": True},
            }
        }
    )
    assert envs["production"].consolidated_secret == "app-config"
    assert envs["local"].consolidated_secret is None


def test_parse_environments_rejects_blank_consolidated_secret():
    with pytest.raises(ValueError, match="consolidated_secret"):
        parse_environments(
            {
                "environments": {
                    "production": {
                        "origin": "gcp",
                        "gcp_project_id": "notorios",
                        "consolidated_secret": "  ",
                    }
                }
            }
        )


@pytest.fixture()
def config_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
environments:
  production:
    origin: gcp
    gcp_project_id: notorios
    consolidated_secret: app-config
  local:
    origin: local
    dotenv_path: .env
    default: true

variables:
  DB_USER:
    source: DB_USER
  DB_PASSWORD:
    source: DB_PASSWORD
  API_TIMEOUT:
    type: int
    default: 30
"""
    )
    return config


def test_manager_uses_consolidated_secret_from_environment(
    config_file, mocker, monkeypatch
):
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("CONSOLIDATED_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    client = _mock_gcp_client(
        mocker,
        {"app-config": json.dumps({"DB_USER": "svc", "DB_PASSWORD": "hunter2"})},
    )

    manager = ConfigManager(str(config_file))

    assert manager.get("DB_USER") == "svc"
    assert manager.get("DB_PASSWORD") == "hunter2"
    assert manager.get("API_TIMEOUT") == 30
    client.access_secret_version.assert_called_once()


def test_manager_uses_consolidated_secret_from_env_var(
    config_file, mocker, monkeypatch
):
    """SECRET_ORIGIN=gcp + CONSOLIDATED_SECRET env var (juan/odoo-engine style)."""
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("SECRET_ORIGIN", "gcp")
    monkeypatch.setenv("GCP_PROJECT_ID", "notorios")
    monkeypatch.setenv("CONSOLIDATED_SECRET", "app-config")
    client = _mock_gcp_client(
        mocker,
        {"app-config": json.dumps({"DB_USER": "svc", "DB_PASSWORD": "hunter2"})},
    )

    manager = ConfigManager(str(config_file), dotenv_path=None)

    assert manager.get("DB_USER") == "svc"
    assert manager.get("DB_PASSWORD") == "hunter2"
    client.access_secret_version.assert_called_once()


def test_manager_without_consolidated_secret_behaves_as_before(
    config_file, mocker, monkeypatch
):
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("CONSOLIDATED_SECRET", raising=False)
    monkeypatch.setenv("SECRET_ORIGIN", "gcp")
    monkeypatch.setenv("GCP_PROJECT_ID", "notorios")
    client = _mock_gcp_client(
        mocker,
        {"DB_USER": "svc", "DB_PASSWORD": "hunter2"},
    )

    manager = ConfigManager(str(config_file), dotenv_path=None)

    assert manager.get("DB_USER") == "svc"
    assert manager.get("DB_PASSWORD") == "hunter2"
    assert client.access_secret_version.call_count == 2
