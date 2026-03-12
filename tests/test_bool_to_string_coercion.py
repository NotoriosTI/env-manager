"""Test scalar-to-string coercion via ConfigManager when type is str."""

from __future__ import annotations

import pytest

from env_manager import ConfigManager
from conftest import write_config


@pytest.mark.parametrize("yaml_value,expected", [("true", "true"), ("false", "false")])
def test_bool_yaml_to_string(tmp_path, yaml_value, expected):
    """YAML unquoted booleans coerce to lowercase string when type is str."""
    config = write_config(
        tmp_path,
        f"""
        variables:
          FLAG:
            default: {yaml_value}
            type: str
        validation:
          strict: false
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(str(config), dotenv_path=str(env_file), auto_load=True)
    result = manager.get("FLAG")
    assert result == expected
    assert isinstance(result, str)


def test_number_to_string(tmp_path):
    """YAML integer default coerces to string when type is str."""
    config = write_config(
        tmp_path,
        """
        variables:
          PORT:
            default: 8080
            type: str
        validation:
          strict: false
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(str(config), dotenv_path=str(env_file), auto_load=True)
    result = manager.get("PORT")
    assert result == "8080"
    assert isinstance(result, str)
