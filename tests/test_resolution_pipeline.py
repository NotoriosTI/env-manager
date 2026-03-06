"""Acceptance tests for sourced variable precedence."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

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
