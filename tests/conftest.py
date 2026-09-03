"""Test configuration for env-manager."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from textwrap import dedent

import pytest

import env_manager.manager as manager_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests start with a clean slate for key env variables."""
    manager_module._SINGLETON = None
    for key in (
        "DB_PASSWORD",
        "PORT",
        "DEBUG_MODE",
        "TIMEOUT",
        "GCP_PROJECT_ID",
        "SECRET_ORIGIN",
        "CONSOLIDATED_SECRET",
        "API_KEY",
        "OPTIONAL",
        "WORKERS",
        "ENVIRONMENT",
        "DEFAULT_TOKEN",
        "OVERRIDE_TOKEN",
        "PINNED_SECRET",
        "GCP_SECRET",
        "SHARED_TOKEN",
        "OVERRIDDEN_TOKEN",
        "LOCAL_ONLY_TOKEN",
        "OPTIONAL_TOKEN",
        "API_TOKEN",
        "PROD_LOCAL_TOKEN",
        "DOTENV_PRIVATE_KEY",
        "DOTENV_PRIVATE_KEY_PRODUCTION",
        "DOTENV_PRIVATE_KEY_STAGING",
        "DOTENV_PRIVATE_KEY_STAGING_BLUE",
        "APP_ENV",
        "HELLO",
        "PLAIN",
        "DOTENV_PUBLIC_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    manager_module._SINGLETON = None


# ---------------------------------------------------------------------------
# Shared helper functions for writing test fixtures
# ---------------------------------------------------------------------------


def write_config(tmp_path: Path, yaml_text: str) -> Path:
    """Write dedented yaml_text to tmp_path/config.yaml and return the path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dedent(yaml_text), encoding="utf-8")
    return config_path


def write_env(tmp_path: Path, content: str = "DB_PASSWORD=secret123\n") -> Path:
    """Write content to tmp_path/.env and return the path."""
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def write_repo_config(repo_root: Path, yaml_text: str) -> Path:
    """Write a minimal pyproject.toml to repo_root, create repo_root/config/,
    write dedented yaml to config.yaml inside it, and return the config path.
    """
    (repo_root / "pyproject.toml").write_text(
        "[project]\nname='test-app'\n", encoding="utf-8"
    )
    config_dir = repo_root / "config"
    config_dir.mkdir()
    return write_config(config_dir, yaml_text)


# ---------------------------------------------------------------------------
# Fixtures de dotenv cifrado, compartidas por varios módulos de test.
#
# No hay material de llave commiteado en este repositorio: la llave se genera
# fresca al arrancar la sesión de tests y los archivos cifrados se producen en
# tiempo de ejecución. Antes vivían en tests/fixtures/.env.encrypted, que se
# eliminó junto con su llave privada en a8cbf7c.
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
