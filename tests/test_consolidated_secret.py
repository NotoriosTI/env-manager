"""Tests for consolidated-secret support (one JSON secret per app)."""

import json
import logging

import pytest
from google.api_core import exceptions as gcp_exceptions

from env_manager.environment import parse_environments
from env_manager.loaders import GCPSecretLoader
from env_manager.manager import ConfigManager, init_config


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


def test_get_many_deduplicates_lookups_and_summarizes_batch(mocker, caplog):
    client = _mock_gcp_client(
        mocker,
        {
            "app-config": json.dumps({"DB_USER": "svc"}),
            "EXTRA_KEY": "individual-value",
        },
    )
    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        values = loader.get_many(["DB_USER", "EXTRA_KEY", "EXTRA_KEY", "MISSING"])

    assert values == {
        "DB_USER": "svc",
        "EXTRA_KEY": "individual-value",
        "MISSING": None,
    }
    assert client.access_secret_version.call_count == 3
    summary = next(
        record.message for record in caplog.records if "load summary" in record.message
    )
    assert "preloaded=1" in summary
    assert "resolved_from_consolidated=1" in summary
    assert "individual_accesses=2" in summary
    assert "missing=1" in summary
    assert "DB_USER" not in summary
    assert "EXTRA_KEY" not in summary
    assert "MISSING" not in summary
    assert "Secret 'MISSING' not found" not in caplog.text


def test_get_many_logs_info_when_every_key_is_consolidated(mocker, caplog):
    client = _mock_gcp_client(
        mocker,
        {"app-config": json.dumps({"EMPTY": "", "DB_USER": "svc"})},
    )
    loader = GCPSecretLoader(project_id="p", consolidated_secret="app-config")

    with caplog.at_level(logging.INFO, logger="env-manager"):
        values = loader.get_many(["EMPTY", "DB_USER", "EMPTY"])

    assert values == {"EMPTY": "", "DB_USER": "svc"}
    assert client.access_secret_version.call_count == 1
    summary_record = next(
        record for record in caplog.records if "load summary" in record.message
    )
    assert summary_record.levelno == logging.INFO
    assert "preloaded=2" in summary_record.message
    assert "resolved_from_consolidated=2" in summary_record.message
    assert "individual_accesses=0" in summary_record.message
    assert "missing=0" in summary_record.message


def test_get_many_warns_when_a_cached_value_did_not_come_from_consolidated(
    mocker, caplog
):
    client = _mock_gcp_client(mocker, {"INDIVIDUAL": "value"})
    loader = GCPSecretLoader(project_id="p")
    assert loader.get("INDIVIDUAL") == "value"

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        assert loader.get_many(["INDIVIDUAL"]) == {"INDIVIDUAL": "value"}

    summary_record = next(
        record for record in caplog.records if "load summary" in record.message
    )
    assert summary_record.levelno == logging.WARNING
    assert "individual_accesses=0" in summary_record.message


def test_get_many_without_fallback_never_accesses_individual_secrets(
    mocker, caplog
):
    client = _mock_gcp_client(
        mocker,
        {"app-config": json.dumps({"DB_USER": "svc"}), "EXTRA_KEY": "unused"},
    )
    loader = GCPSecretLoader(
        project_id="p",
        consolidated_secret="app-config",
        fallback_to_individual=False,
    )

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        values = loader.get_many(["DB_USER", "EXTRA_KEY"])

    assert values == {"DB_USER": "svc", "EXTRA_KEY": None}
    client.access_secret_version.assert_called_once()
    assert "individual_accesses=0" in caplog.text
    assert "missing=1" in caplog.text
    assert "fallback_to_individual=false" in caplog.text


@pytest.mark.parametrize(
    "secrets, message",
    [
        ({}, "not found"),
        ({"app-config": "not json {"}, "not valid JSON"),
        ({"app-config": json.dumps(["not", "an", "object"])}, "JSON object"),
    ],
)
def test_invalid_or_missing_consolidated_secret_is_fatal_without_fallback(
    mocker, secrets, message
):
    client = _mock_gcp_client(mocker, secrets)
    loader = GCPSecretLoader(
        project_id="p",
        consolidated_secret="app-config",
        fallback_to_individual=False,
    )

    with pytest.raises(RuntimeError, match=message):
        loader.get_many(["DB_USER"])
    with pytest.raises(RuntimeError, match=message):
        loader.get("DB_USER")

    client.access_secret_version.assert_called_once()


def test_direct_get_still_warns_when_individual_secret_is_missing(mocker, caplog):
    _mock_gcp_client(mocker, {})
    loader = GCPSecretLoader(project_id="p")

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        assert loader.get("MISSING") is None

    assert "Secret 'MISSING' not found" in caplog.text


def test_loader_rejects_disabled_fallback_without_consolidated_secret():
    with pytest.raises(ValueError, match="requires a consolidated_secret"):
        GCPSecretLoader(project_id="p", fallback_to_individual=False)


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
    assert envs["production"].fallback_to_individual is True


def test_parse_environments_accepts_disabled_individual_fallback():
    envs = parse_environments(
        {
            "environments": {
                "production": {
                    "origin": "gcp",
                    "gcp_project_id": "notorios",
                    "consolidated_secret": "app-config",
                    "fallback_to_individual": False,
                }
            }
        }
    )

    assert envs["production"].fallback_to_individual is False


@pytest.mark.parametrize("fallback", [False, "false", 0])
def test_parse_environments_validates_individual_fallback(fallback):
    config = {
        "environments": {
            "production": {
                "origin": "gcp",
                "gcp_project_id": "notorios",
                "fallback_to_individual": fallback,
            }
        }
    }

    message = (
        "requires 'consolidated_secret'"
        if fallback is False
        else "must be a boolean"
    )
    with pytest.raises(ValueError, match=message):
        parse_environments(config)


def test_local_environment_rejects_disabled_individual_fallback():
    with pytest.raises(ValueError, match="requires 'consolidated_secret'"):
        parse_environments(
            {
                "environments": {
                    "local": {
                        "origin": "local",
                        "fallback_to_individual": False,
                    }
                }
            }
        )


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


def test_manager_propagates_yaml_fallback_setting(tmp_path, mocker, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
environments:
  production:
    origin: gcp
    gcp_project_id: notorios
    consolidated_secret: app-config
    fallback_to_individual: false
    default: true
variables:
  DB_USER:
    source: DB_USER
  EXTRA_KEY:
    source: EXTRA_KEY
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("EXTRA_KEY", raising=False)
    client = _mock_gcp_client(
        mocker, {"app-config": json.dumps({"DB_USER": "svc"}), "EXTRA_KEY": "unused"}
    )

    manager = ConfigManager(str(config))

    assert manager.fallback_to_individual is False
    assert manager.get("DB_USER") == "svc"
    assert manager.get("EXTRA_KEY") is None
    client.access_secret_version.assert_called_once()


def test_init_config_accepts_fallback_override(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("variables: {}\n", encoding="utf-8")
    monkeypatch.setenv("CONSOLIDATED_SECRET", "app-config")

    manager = init_config(
        str(config), auto_load=False, fallback_to_individual=False
    )

    assert manager.fallback_to_individual is False


def test_manager_rejects_disabled_fallback_without_consolidated_secret(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("variables: {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires a consolidated_secret"):
        ConfigManager(
            str(config), auto_load=False, fallback_to_individual=False
        )


def test_local_origin_does_not_warn_when_gcp_project_is_missing(
    tmp_path, caplog, monkeypatch
):
    config = tmp_path / "config.yaml"
    config.write_text("variables: {}\n", encoding="utf-8")
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("SECRET_ORIGIN", raising=False)

    with caplog.at_level(logging.WARNING, logger="env-manager"):
        ConfigManager(str(config), auto_load=False, secret_origin="local")

    assert "GCP_PROJECT_ID not set" not in caplog.text
