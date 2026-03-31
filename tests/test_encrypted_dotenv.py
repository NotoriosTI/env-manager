"""Red regression tests for encrypted dotenv support (ENC-01 through ENC-04).

These tests define the expected behavior for Phase 02 encrypted dotenv.
They MUST fail until the implementation is complete.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from env_manager.exceptions import DecryptionError, DecryptionIssue
from env_manager.loaders.dotenv import DotEnvLoader

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOTENVX_PRIVATE_KEY = "81dac4d2c42e67a2c6542d3b943a4674a05c4be5e7e5a40a689be7a3bd49a07e"


# ---------------------------------------------------------------------------
# ENC-02: dotenvx encrypted: values decrypt correctly
# ---------------------------------------------------------------------------

class TestEncryptedDecryption:
    """DotEnvLoader with encrypted=True decrypts encrypted: prefixed values."""

    def test_decrypt_known_ciphertext(self):
        """Known dotenvx ciphertext decrypts to 'world'."""
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=DOTENVX_PRIVATE_KEY,
        )
        assert loader.get("HELLO") == "world"

    def test_plaintext_values_pass_through(self):
        """Non-encrypted values returned as-is when encrypted=True."""
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=DOTENVX_PRIVATE_KEY,
        )
        assert loader.get("PLAIN") == "still-plain"

    def test_dotenv_public_key_passes_through(self):
        """DOTENV_PUBLIC_KEY is never decrypted even with encrypted=True."""
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=DOTENVX_PRIVATE_KEY,
        )
        result = loader.get("DOTENV_PUBLIC_KEY")
        assert result is not None
        assert result.startswith("03")


# ---------------------------------------------------------------------------
# ENC-01: plaintext environments unaffected by default
# ---------------------------------------------------------------------------

class TestPlaintextUnchanged:
    """Plaintext loaders keep current behavior when encrypted is not set."""

    def test_plaintext_loader_ignores_encrypted_prefix(self, tmp_path):
        """Without encrypted=True, encrypted: values are returned raw."""
        env_file = tmp_path / ".env"
        env_file.write_text('HELLO="encrypted:abc123"\n')
        loader = DotEnvLoader(dotenv_path=str(env_file))
        # Without encrypted=True, the raw value is returned including prefix
        assert loader.get("HELLO") == '"encrypted:abc123"' or loader.get("HELLO") == "encrypted:abc123"


# ---------------------------------------------------------------------------
# ENC-03: DecryptionError raised on invalid/missing key
# ---------------------------------------------------------------------------

class TestDecryptionErrors:
    """DecryptionError raised when encrypted values cannot be decrypted."""

    def test_missing_private_key_raises_decryption_error(self, tmp_path, monkeypatch):
        """No key available -> DecryptionError with issue per failed variable."""
        for k in ("DOTENV_PRIVATE_KEY", "DOTENV_PRIVATE_KEY_PRODUCTION"):
            monkeypatch.delenv(k, raising=False)
        # Copy encrypted file to tmp_path (no .env.keys present) so no key can be found
        import shutil
        env_file = tmp_path / ".env.encrypted"
        shutil.copy(FIXTURES / ".env.encrypted", env_file)
        loader = DotEnvLoader(
            dotenv_path=str(env_file),
            encrypted=True,
        )
        with pytest.raises(DecryptionError) as exc_info:
            loader.get("HELLO")
        assert len(exc_info.value.issues) >= 1
        assert exc_info.value.issues[0].key == "HELLO"

    def test_wrong_private_key_raises_decryption_error(self):
        """Wrong key -> DecryptionError (decryption fails)."""
        wrong_key = "0000000000000000000000000000000000000000000000000000000000000001"
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=wrong_key,
        )
        with pytest.raises(DecryptionError) as exc_info:
            loader.get("HELLO")
        assert len(exc_info.value.issues) >= 1

    def test_get_many_aggregates_decryption_errors(self, tmp_path, monkeypatch):
        """get_many collects all failures into one DecryptionError."""
        for k in ("DOTENV_PRIVATE_KEY", "DOTENV_PRIVATE_KEY_PRODUCTION"):
            monkeypatch.delenv(k, raising=False)
        # Copy encrypted file to tmp_path (no .env.keys present) so no key can be found
        import shutil
        env_file = tmp_path / ".env.encrypted"
        shutil.copy(FIXTURES / ".env.encrypted", env_file)
        loader = DotEnvLoader(
            dotenv_path=str(env_file),
            encrypted=True,
        )
        with pytest.raises(DecryptionError) as exc_info:
            loader.get_many(["HELLO"])
        assert len(exc_info.value.issues) >= 1


# ---------------------------------------------------------------------------
# ENC-04: private key resolution order
# ---------------------------------------------------------------------------

class TestKeyResolutionOrder:
    """Private key resolved via env-specific -> generic -> .env.keys file."""

    def test_env_specific_key_takes_precedence(self, monkeypatch):
        """DOTENV_PRIVATE_KEY_PRODUCTION tried before DOTENV_PRIVATE_KEY."""
        monkeypatch.setenv("DOTENV_PRIVATE_KEY_PRODUCTION", DOTENVX_PRIVATE_KEY)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_generic_key_used_when_no_env_specific(self, monkeypatch):
        """DOTENV_PRIVATE_KEY used when no env-specific key exists."""
        monkeypatch.setenv("DOTENV_PRIVATE_KEY", DOTENVX_PRIVATE_KEY)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY_PRODUCTION", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_env_keys_file_used_as_last_resort(self, monkeypatch):
        """Colocated .env.keys file used when no env vars set."""
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY_PRODUCTION", raising=False)
        # The fixture .env.keys is colocated with .env.encrypted in tests/fixtures/
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_explicit_private_key_overrides_all(self, monkeypatch):
        """explicit_private_key kwarg overrides the entire resolution chain."""
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(FIXTURES / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=DOTENVX_PRIVATE_KEY,
        )
        assert loader.get("HELLO") == "world"
