"""Acceptance tests for sourced variable precedence."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import env_manager.manager as manager_module
from env_manager import ConfigManager


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dedent(yaml_text), encoding="utf-8")
    return config_path


def test_sourced_value_prefers_os_environ_over_active_environment_dotenv(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("API_KEY", "from-os")

    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
          staging:
            origin: local
            dotenv_path: .env.staging
        variables:
          API_KEY:
            source: API_KEY
        validation:
          strict: false
        """,
    )
    (tmp_path / ".env.staging").write_text("API_KEY=from-dotenv\n", encoding="utf-8")

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.active_environment is not None
    assert manager.active_environment.name == "staging"
    assert manager.get("API_KEY") == "from-os"


def test_sourced_value_uses_active_environment_dotenv_when_os_environ_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("API_KEY", raising=False)

    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
          staging:
            origin: local
            dotenv_path: .env.staging
        variables:
          API_KEY:
            source: API_KEY
        validation:
          strict: false
        """,
    )
    (tmp_path / ".env.staging").write_text("API_KEY=from-dotenv\n", encoding="utf-8")

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("API_KEY") == "from-dotenv"


def test_sourced_value_falls_back_to_yaml_default_after_os_environ_and_dotenv(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("PORT", raising=False)

    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
          staging:
            origin: local
            dotenv_path: .env.staging
        variables:
          PORT:
            source: PORT
            type: int
            default: 8080
        validation:
          strict: false
        """,
    )
    (tmp_path / ".env.staging").write_text("", encoding="utf-8")

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("PORT") == 8080


def test_variable_origin_override_uses_gcp_loader_while_active_environment_is_local(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
        variables:
          API_KEY:
            source: projects/app-prod/secrets/API_KEY
            origin: gcp
        validation:
          strict: false
        """,
    )

    seen: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []

    class FakeLoader:
        def get_many(self, keys):
            seen.append(("gcp", "app-prod", None, tuple(keys)))
            return {key: "from-gcp" for key in keys}

    def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None):
        assert origin == "gcp"
        assert gcp_project_id == "app-prod"
        assert dotenv_path is None
        return FakeLoader()

    monkeypatch.setenv("GCP_PROJECT_ID", "app-prod")
    monkeypatch.setattr(manager_module, "create_loader", fake_create_loader)

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("API_KEY") == "from-gcp"
    assert seen == [("gcp", "app-prod", None, ("projects/app-prod/secrets/API_KEY",))]


def test_os_environ_beats_pinned_environment_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("API_KEY", "from-os")

    config_path = _write_config(
        tmp_path,
        """
        environments:
          staging:
            origin: local
            dotenv_path: .env.staging
          production:
            origin: local
            dotenv_path: .env.production
        variables:
          API_KEY:
            source: API_KEY
            environment: production
        validation:
          strict: false
        """,
    )
    (tmp_path / ".env.production").write_text("API_KEY=from-pinned\n", encoding="utf-8")

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("API_KEY") == "from-os"


def test_variables_without_overrides_keep_active_environment_behavior(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("SHARED_TOKEN", raising=False)
    monkeypatch.delenv("OVERRIDDEN_TOKEN", raising=False)

    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
          staging:
            origin: local
            dotenv_path: .env.staging
          production:
            origin: local
            dotenv_path: .env.production
        variables:
          SHARED_TOKEN:
            source: SHARED_TOKEN
          OVERRIDDEN_TOKEN:
            source: OVERRIDDEN_TOKEN
            environment: production
        validation:
          strict: false
        """,
    )
    (tmp_path / ".env.staging").write_text("SHARED_TOKEN=from-staging\n", encoding="utf-8")
    (tmp_path / ".env.production").write_text(
        "OVERRIDDEN_TOKEN=from-production\n", encoding="utf-8"
    )

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("SHARED_TOKEN") == "from-staging"
    assert manager.get("OVERRIDDEN_TOKEN") == "from-production"
