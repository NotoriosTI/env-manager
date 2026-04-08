"""Red regression tests for encrypted dotenv support (ENC-01 through ENC-04).

These tests define the expected behavior for Phase 02 encrypted dotenv.
They MUST fail until the implementation is complete.

NOTE: No private key material is committed to this repository.
An ephemeral secp256k1 keypair is generated fresh at test-session startup.
All encrypted fixtures are produced at runtime using that ephemeral key and
discarded afterwards.
"""
from __future__ import annotations

import base64
import shutil

import pytest

from env_manager.exceptions import DecryptionError
from env_manager.loaders.dotenv import DotEnvLoader


# ---------------------------------------------------------------------------
# Ephemeral keypair + fixture helpers
# ---------------------------------------------------------------------------

def _generate_keypair() -> tuple[str, str]:
    """Return (private_key_hex, public_key_hex) for a fresh secp256k1 keypair."""
    import coincurve  # installed via eciespy dependency

    sk = coincurve.PrivateKey()
    private_key_hex = sk.secret.hex()
    public_key_hex = sk.public_key.format(compressed=True).hex()
    return private_key_hex, public_key_hex


def _encrypt_value(public_key_hex: str, plaintext: str) -> str:
    """Encrypt *plaintext* with *public_key_hex*; return ``encrypted:<b64>``."""
    from ecies import encrypt as ecies_encrypt

    cipher_bytes = ecies_encrypt(public_key_hex, plaintext.encode("utf-8"))
    return "encrypted:" + base64.b64encode(cipher_bytes).decode("ascii")


@pytest.fixture(scope="session")
def ephemeral_keys() -> tuple[str, str]:
    """Session-scoped ephemeral secp256k1 keypair (private_hex, public_hex)."""
    return _generate_keypair()


@pytest.fixture(scope="session")
def encrypted_fixture_dir(tmp_path_factory, ephemeral_keys):
    """Create a temp directory with .env.encrypted and .env.keys files.

    The files are generated from the ephemeral keypair so no real key material
    ever lands in the repository.
    """
    private_key_hex, public_key_hex = ephemeral_keys
    fixture_dir = tmp_path_factory.mktemp("fixtures")

    hello_encrypted = _encrypt_value(public_key_hex, "world")

    env_encrypted = fixture_dir / ".env.encrypted"
    env_encrypted.write_text(
        f'DOTENV_PUBLIC_KEY="{public_key_hex}"\n'
        f'HELLO="{hello_encrypted}"\n'
        'PLAIN=still-plain\n',
        encoding="utf-8",
    )

    env_keys = fixture_dir / ".env.keys"
    env_keys.write_text(
        "#/------------------!DOTENV_PRIVATE_KEYS!-------------------/\n"
        "#/   private decryption keys. DO NOT commit to source control /\n"
        "#/----------------------------------------------------------/\n"
        f'DOTENV_PRIVATE_KEY="{private_key_hex}"\n',
        encoding="utf-8",
    )

    return fixture_dir


# ---------------------------------------------------------------------------
# ENC-02: dotenvx encrypted: values decrypt correctly
# ---------------------------------------------------------------------------

class TestEncryptedDecryption:
    """DotEnvLoader with encrypted=True decrypts encrypted: prefixed values."""

    def test_decrypt_known_ciphertext(self, encrypted_fixture_dir, ephemeral_keys):
        """Ciphertext produced with ephemeral key decrypts to 'world'."""
        private_key_hex, _ = ephemeral_keys
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=private_key_hex,
        )
        assert loader.get("HELLO") == "world"

    def test_plaintext_values_pass_through(self, encrypted_fixture_dir, ephemeral_keys):
        """Non-encrypted values returned as-is when encrypted=True."""
        private_key_hex, _ = ephemeral_keys
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=private_key_hex,
        )
        assert loader.get("PLAIN") == "still-plain"

    def test_dotenv_public_key_passes_through(self, encrypted_fixture_dir, ephemeral_keys):
        """DOTENV_PUBLIC_KEY is never decrypted even with encrypted=True."""
        private_key_hex, _ = ephemeral_keys
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=private_key_hex,
        )
        result = loader.get("DOTENV_PUBLIC_KEY")
        assert result is not None
        # Compressed secp256k1 public keys start with 02 or 03
        assert result.startswith("02") or result.startswith("03")


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

    def test_missing_private_key_raises_decryption_error(self, encrypted_fixture_dir, tmp_path, monkeypatch):
        """No key available -> DecryptionError with issue per failed variable."""
        for k in ("DOTENV_PRIVATE_KEY", "DOTENV_PRIVATE_KEY_PRODUCTION"):
            monkeypatch.delenv(k, raising=False)
        # Copy only the encrypted file to tmp_path (no .env.keys present) so no key can be found
        env_file = tmp_path / ".env.encrypted"
        shutil.copy(encrypted_fixture_dir / ".env.encrypted", env_file)
        loader = DotEnvLoader(
            dotenv_path=str(env_file),
            encrypted=True,
        )
        with pytest.raises(DecryptionError) as exc_info:
            loader.get("HELLO")
        assert len(exc_info.value.issues) >= 1
        assert exc_info.value.issues[0].key == "HELLO"

    def test_wrong_private_key_raises_decryption_error(self, encrypted_fixture_dir):
        """Wrong key -> DecryptionError (decryption fails)."""
        wrong_key = "0000000000000000000000000000000000000000000000000000000000000001"
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=wrong_key,
        )
        with pytest.raises(DecryptionError) as exc_info:
            loader.get("HELLO")
        assert len(exc_info.value.issues) >= 1

    def test_get_many_aggregates_decryption_errors(self, encrypted_fixture_dir, tmp_path, monkeypatch):
        """get_many collects all failures into one DecryptionError."""
        for k in ("DOTENV_PRIVATE_KEY", "DOTENV_PRIVATE_KEY_PRODUCTION"):
            monkeypatch.delenv(k, raising=False)
        # Copy only the encrypted file to tmp_path (no .env.keys present) so no key can be found
        env_file = tmp_path / ".env.encrypted"
        shutil.copy(encrypted_fixture_dir / ".env.encrypted", env_file)
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

    def test_env_specific_key_takes_precedence(self, encrypted_fixture_dir, ephemeral_keys, monkeypatch):
        """DOTENV_PRIVATE_KEY_PRODUCTION tried before DOTENV_PRIVATE_KEY."""
        private_key_hex, _ = ephemeral_keys
        monkeypatch.setenv("DOTENV_PRIVATE_KEY_PRODUCTION", private_key_hex)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_generic_key_used_when_no_env_specific(self, encrypted_fixture_dir, ephemeral_keys, monkeypatch):
        """DOTENV_PRIVATE_KEY used when no env-specific key exists."""
        private_key_hex, _ = ephemeral_keys
        monkeypatch.setenv("DOTENV_PRIVATE_KEY", private_key_hex)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY_PRODUCTION", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_env_keys_file_used_as_last_resort(self, encrypted_fixture_dir, monkeypatch):
        """Colocated .env.keys file used when no env vars set."""
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("DOTENV_PRIVATE_KEY_PRODUCTION", raising=False)
        # encrypted_fixture_dir already has a colocated .env.keys file
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            environment_name="production",
        )
        assert loader.get("HELLO") == "world"

    def test_explicit_private_key_overrides_all(self, encrypted_fixture_dir, ephemeral_keys, monkeypatch):
        """explicit_private_key kwarg overrides the entire resolution chain."""
        private_key_hex, _ = ephemeral_keys
        monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
        loader = DotEnvLoader(
            dotenv_path=str(encrypted_fixture_dir / ".env.encrypted"),
            encrypted=True,
            explicit_private_key=private_key_hex,
        )
        assert loader.get("HELLO") == "world"
