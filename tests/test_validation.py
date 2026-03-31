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


# ---------------------------------------------------------------------------
# ENC-03: DecryptionError public export isinstance check
# ---------------------------------------------------------------------------

def test_decryption_error_isinstance_check():
    """DecryptionError can be imported and isinstance-checked."""
    from env_manager import DecryptionError
    from env_manager.exceptions import DecryptionIssue

    issues = [DecryptionIssue(key="SECRET", message="no key")]
    err = DecryptionError(issues)

    assert isinstance(err, DecryptionError)
    assert isinstance(err, Exception)
    assert len(err.issues) == 1
    assert err.issues[0].key == "SECRET"
    assert "SECRET" in str(err)
