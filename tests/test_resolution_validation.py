from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    manager_module._SINGLETON = None
    for key in ("API_KEY", "OPTIONAL_TOKEN", "API_TOKEN", "GCP_PROJECT_ID"):
        monkeypatch.delenv(key, raising=False)
    yield
    manager_module._SINGLETON = None


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dedent(yaml_text), encoding="utf-8")
    return config_path


def test_required_sourced_variable_missing_raises_runtime_error_with_context(
    tmp_path, capsys
):
    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env.runtime
        variables:
          API_KEY:
            source: API_KEY
        validation:
          required:
            - API_KEY
        """,
    )
    (tmp_path / ".env.runtime").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc.value)
    assert "Required variable 'API_KEY' not found" in message
    assert "environment 'default'" in message
    assert str((tmp_path / ".env.runtime").resolve()) in message
    assert "API_KEY" in capsys.readouterr().out


def test_required_sourced_variable_uses_yaml_default_and_warns(tmp_path, capsys):
    config_path = _write_config(
        tmp_path,
        """
        variables:
          API_KEY:
            source: API_KEY
            default: "fallback-key"
        validation:
          required:
            - API_KEY
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("API_KEY") == "fallback-key"
    output = capsys.readouterr().out
    assert "Required variable 'API_KEY' missing from source; using YAML default" in output
    assert "environment 'default'" in output


def test_optional_sourced_variable_without_default_resolves_none_and_warns(
    tmp_path, capsys
):
    config_path = _write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
        validation:
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("OPTIONAL_TOKEN") is None
    output = capsys.readouterr().out
    assert "Optional variable 'OPTIONAL_TOKEN' resolved to None" in output
    assert "environment 'default'" in output


def test_optional_sourced_variable_with_yaml_default_is_quiet(tmp_path, capsys):
    config_path = _write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
            default: "quiet-default"
        validation:
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("OPTIONAL_TOKEN") == "quiet-default"
    output = capsys.readouterr().out
    assert "Optional variable 'OPTIONAL_TOKEN'" not in output


def test_strict_mode_raises_before_optional_fallback(tmp_path):
    config_path = _write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
        validation:
          strict: true
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(
            str(config_path),
            secret_origin="local",
            dotenv_path=str(env_file),
            auto_load=True,
        )

    assert "Strict mode" in str(exc.value)


def test_gcp_runtime_context_is_included_in_missing_value_messages(
    tmp_path, monkeypatch, capsys
):
    config_path = _write_config(
        tmp_path,
        """
        environments:
          default:
            origin: gcp
            gcp_project_id: app-prod
        variables:
          API_TOKEN:
            source: projects/app-prod/secrets/API_TOKEN
        validation:
          optional:
            - API_TOKEN
        """,
    )

    class FakeLoader:
        def get_many(self, keys):
            return {key: None for key in keys}

    monkeypatch.setattr(
        manager_module,
        "create_loader",
        lambda *args, **kwargs: FakeLoader(),
    )

    manager = ConfigManager(
        str(config_path),
        gcp_project_id="app-prod",
        auto_load=True,
    )

    assert manager.get("API_TOKEN") is None
    output = capsys.readouterr().out
    assert "environment 'default'" in output
    assert "GCP project 'app-prod'" in output
