from __future__ import annotations

import pytest

from env_manager import ConfigManager
from conftest import write_config


def test_strict_override_disables_strict(tmp_path):
    config = write_config(
        tmp_path,
        """
        variables:
          OPTIONAL:
            source: OPTIONAL
        validation:
          strict: true
        """,
    )

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config),
        secret_origin="local",
        dotenv_path=str(env_file),
        strict=False,
    )

    assert manager.get("OPTIONAL") is None
