"""Regression tests for default-only variable behavior."""

from __future__ import annotations

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager
from conftest import write_config


def test_default_only_variables_resolve_from_yaml_without_loader(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("LOG_LEVEL", "TRACE")

    config_path = write_config(
        tmp_path,
        """
        variables:
          LOG_LEVEL:
            type: str
            default: "INFO"
          DEBUG_MODE:
            type: bool
            default: false
        validation:
          strict: false
        """,
    )

    def fail_create_loader(*args, **kwargs):
        raise AssertionError("default-only config should not create a loader")

    monkeypatch.setattr(manager_module, "create_loader", fail_create_loader)

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("LOG_LEVEL") == "INFO"
    assert manager.get("DEBUG_MODE") is False
    assert "Loaded LOG_LEVEL" in capsys.readouterr().out


def test_default_only_variable_ignores_same_named_os_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMEOUT", "99")

    config_path = write_config(
        tmp_path,
        """
        variables:
          TIMEOUT:
            type: int
            default: 30
        validation:
          strict: false
        """,
    )

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("TIMEOUT") == 30


def test_variable_with_source_and_default_uses_loader_value(tmp_path):
    config_path = write_config(
        tmp_path,
        """
        variables:
          PORT:
            source: PORT
            type: int
            default: 8080
        validation:
          strict: false
        """,
    )
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("PORT=9000\n", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        dotenv_path=str(dotenv_file),
        auto_load=True,
    )

    assert manager.get("PORT") == 9000


def test_variable_with_source_and_default_falls_back_to_default(tmp_path):
    config_path = write_config(
        tmp_path,
        """
        variables:
          PORT:
            source: PORT
            type: int
            default: 8080
        validation:
          strict: false
        """,
    )
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        dotenv_path=str(dotenv_file),
        auto_load=True,
    )

    assert manager.get("PORT") == 8080


def test_mixed_config_fetches_only_sourced_variables(tmp_path, monkeypatch):
    config_path = write_config(
        tmp_path,
        """
        variables:
          API_TOKEN:
            source: API_TOKEN
          LOG_LEVEL:
            type: str
            default: "INFO"
        validation:
          strict: false
        """,
    )

    requested_keys: list[str] = []

    class FakeLoader:
        def get_many(self, keys):
            requested_keys.extend(keys)
            return {"API_TOKEN": "top-secret"}

    monkeypatch.setattr(manager_module, "create_loader", lambda *args, **kwargs: FakeLoader())

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("API_TOKEN") == "top-secret"
    assert manager.get("LOG_LEVEL") == "INFO"
    assert requested_keys == ["API_TOKEN"]


def test_variable_with_neither_source_nor_default_raises(tmp_path):
    config_path = write_config(
        tmp_path,
        """
        variables:
          INVALID_VAR:
            type: str
        validation:
          strict: false
        """,
    )

    with pytest.raises(ValueError, match="must define either 'source' or 'default'"):
        ConfigManager(str(config_path), auto_load=True)
