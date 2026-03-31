"""Tests for the env-manager-encrypt CLI encryption module."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from ecies import decrypt as ecies_decrypt

from env_manager.cli.encrypt import encrypt_dotenv_file
from env_manager.loaders.dotenv import DotEnvLoader


class TestKeyGeneration:
    """CLI-01: encrypt generates secp256k1 key pair, writes DOTENV_PUBLIC_KEY."""

    def test_writes_dotenv_public_key_to_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('SECRET=hello\n')
        encrypt_dotenv_file(str(env_file))
        values = dotenv_values(str(env_file))
        pub = values.get("DOTENV_PUBLIC_KEY")
        assert pub is not None
        assert len(pub) == 66  # compressed secp256k1 public key hex

    def test_public_key_starts_with_02_or_03(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('A=1\n')
        encrypt_dotenv_file(str(env_file))
        pub = dotenv_values(str(env_file))["DOTENV_PUBLIC_KEY"]
        assert pub[:2] in ("02", "03")

    def test_env_file_has_dotenvx_header(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('A=1\n')
        encrypt_dotenv_file(str(env_file))
        content = env_file.read_text()
        assert "#/-------------------[DOTENV_PUBLIC_KEY]--------------------/" in content
        assert "#/            public-key encryption for .env files          /" in content
        assert "#/----------------------------------------------------------/" in content


class TestValueEncryption:
    """CLI-02: each plaintext value rewritten as encrypted:<base64> that decrypts back."""

    def test_plaintext_values_become_encrypted_prefix(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('SECRET=hello\nDB=postgres\n')
        encrypt_dotenv_file(str(env_file))
        values = dotenv_values(str(env_file))
        assert values["SECRET"].startswith("encrypted:")
        assert values["DB"].startswith("encrypted:")

    def test_encrypted_values_decrypt_to_original(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('SECRET=hello-world\n')
        encrypt_dotenv_file(str(env_file))
        keys_file = tmp_path / ".env.keys"
        kv = dotenv_values(str(keys_file))
        priv_hex = kv["DOTENV_PRIVATE_KEY"]
        enc_values = dotenv_values(str(env_file))
        cipher_b64 = enc_values["SECRET"][len("encrypted:"):]
        cipher_bytes = base64.b64decode(cipher_b64)
        plaintext = ecies_decrypt(priv_hex, cipher_bytes).decode("utf-8")
        assert plaintext == "hello-world"

    def test_multiple_values_all_decrypt_correctly(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('A=alpha\nB=beta\nC=gamma\n')
        encrypt_dotenv_file(str(env_file))
        keys_file = tmp_path / ".env.keys"
        priv_hex = dotenv_values(str(keys_file))["DOTENV_PRIVATE_KEY"]
        enc_values = dotenv_values(str(env_file))
        for key, original in [("A", "alpha"), ("B", "beta"), ("C", "gamma")]:
            cipher_b64 = enc_values[key][len("encrypted:"):]
            plaintext = ecies_decrypt(priv_hex, base64.b64decode(cipher_b64)).decode("utf-8")
            assert plaintext == original


class TestKeysFile:
    """CLI-03: private key written to colocated .env.keys in dotenvx format."""

    def test_env_keys_file_created(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        encrypt_dotenv_file(str(env_file))
        keys_file = tmp_path / ".env.keys"
        assert keys_file.exists()

    def test_env_keys_has_private_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        encrypt_dotenv_file(str(env_file))
        kv = dotenv_values(str(tmp_path / ".env.keys"))
        priv = kv.get("DOTENV_PRIVATE_KEY")
        assert priv is not None
        assert len(priv) == 64  # 32-byte hex

    def test_env_keys_has_dotenvx_header(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        encrypt_dotenv_file(str(env_file))
        content = (tmp_path / ".env.keys").read_text()
        assert "#/------------------!DOTENV_PRIVATE_KEYS!-------------------/" in content
        assert "DO NOT commit to source control" in content

    def test_env_name_produces_suffixed_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        encrypt_dotenv_file(str(env_file), env_name="production")
        kv = dotenv_values(str(tmp_path / ".env.keys"))
        assert "DOTENV_PRIVATE_KEY_PRODUCTION" in kv
        assert len(kv["DOTENV_PRIVATE_KEY_PRODUCTION"]) == 64


class TestSkipAlreadyEncrypted:
    """CLI-04: already encrypted: prefixed values are skipped."""

    def test_already_encrypted_values_unchanged(self, tmp_path):
        env_file = tmp_path / ".env"
        original_enc = "encrypted:AAAA+existing+cipher=="
        env_file.write_text(f'ALREADY="{original_enc}"\nPLAIN=hello\n')
        encrypt_dotenv_file(str(env_file))
        values = dotenv_values(str(env_file))
        assert values["ALREADY"] == original_enc
        assert values["PLAIN"].startswith("encrypted:")


class TestSkipPublicKey:
    """CLI-05: DOTENV_PUBLIC_KEY variable itself is never encrypted."""

    def test_existing_public_key_causes_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('DOTENV_PUBLIC_KEY="03abcd"\nSECRET=val\n')
        with pytest.raises(ValueError, match="already has DOTENV_PUBLIC_KEY"):
            encrypt_dotenv_file(str(env_file))


class TestForceGuard:
    """CLI-06: refuses when .env.keys exists unless force=True."""

    def test_raises_when_keys_file_exists(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        keys_file = tmp_path / ".env.keys"
        keys_file.write_text('existing=data\n')
        with pytest.raises(FileExistsError, match=".env.keys"):
            encrypt_dotenv_file(str(env_file))

    def test_force_overwrites_existing_keys_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('X=1\n')
        keys_file = tmp_path / ".env.keys"
        keys_file.write_text('existing=data\n')
        encrypt_dotenv_file(str(env_file), force=True)
        kv = dotenv_values(str(keys_file))
        assert "DOTENV_PRIVATE_KEY" in kv


class TestRoundTrip:
    """CLI-07: encrypted output round-trips through DotEnvLoader."""

    def test_round_trip_via_dotenv_loader(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('SECRET=my-password\nAPI_KEY=abc123\n')
        encrypt_dotenv_file(str(env_file))
        priv_hex = dotenv_values(str(tmp_path / ".env.keys"))["DOTENV_PRIVATE_KEY"]
        loader = DotEnvLoader(
            dotenv_path=str(env_file),
            encrypted=True,
            explicit_private_key=priv_hex,
        )
        assert loader.get("SECRET") == "my-password"
        assert loader.get("API_KEY") == "abc123"

    def test_round_trip_preserves_plain_values(self, tmp_path):
        env_file = tmp_path / ".env"
        original_enc = "encrypted:AAAA+existing=="
        env_file.write_text(f'ENC="{original_enc}"\nPLAIN=hello\n')
        encrypt_dotenv_file(str(env_file))
        priv_hex = dotenv_values(str(tmp_path / ".env.keys"))["DOTENV_PRIVATE_KEY"]
        loader = DotEnvLoader(
            dotenv_path=str(env_file),
            encrypted=True,
            explicit_private_key=priv_hex,
        )
        assert loader.get("PLAIN") == "hello"
