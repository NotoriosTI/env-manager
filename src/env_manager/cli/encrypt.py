"""Encrypt a .env file using dotenvx-compatible ECIES encryption."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


ENCRYPTED_PREFIX = "encrypted:"

DOTENV_HEADER = (
    '#/-------------------[DOTENV_PUBLIC_KEY]--------------------/\n'
    '#/            public-key encryption for .env files          /\n'
    '#/----------------------------------------------------------/\n'
)

KEYS_HEADER = (
    '#/------------------!DOTENV_PRIVATE_KEYS!-------------------/\n'
    '#/   private decryption keys. DO NOT commit to source control /\n'
    '#/----------------------------------------------------------/\n'
)


def _normalize_env_name(name: str) -> str:
    """Normalize environment name to uppercase identifier for key suffix."""
    return re.sub(r'[^A-Z0-9]+', '_', name.upper())


def encrypt_dotenv_file(
    file_path: str,
    *,
    env_name: Optional[str] = None,
    force: bool = False,
) -> None:
    """Encrypt a plaintext .env file in-place with dotenvx-compatible ECIES.

    Generates a secp256k1 key pair, rewrites plaintext values as
    encrypted:<base64>, writes DOTENV_PUBLIC_KEY to the .env header,
    and outputs the private key to a colocated .env.keys file.

    Parameters
    ----------
    file_path : str
        Path to the .env file to encrypt.
    env_name : str, optional
        Environment name. When set, .env.keys uses
        DOTENV_PRIVATE_KEY_<NORMALIZED> instead of DOTENV_PRIVATE_KEY.
    force : bool
        If True, overwrite existing .env.keys file.

    Raises
    ------
    FileNotFoundError
        If file_path does not exist.
    ValueError
        If the .env file already contains DOTENV_PUBLIC_KEY.
    FileExistsError
        If .env.keys already exists and force is False.
    """
    # -- import eciespy lazily for helpful error when [encrypted] extra missing --
    try:
        from coincurve import PrivateKey
        from ecies import encrypt as ecies_encrypt
    except ImportError:
        raise ImportError(
            "eciespy is required for the encrypt command. "
            "Install it with: pip install env-manager[encrypted]"
        )

    env_path = Path(file_path)
    if not env_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    keys_path = env_path.parent / ".env.keys"
    if keys_path.exists() and not force:
        raise FileExistsError(
            f"{keys_path} already exists. Use --force to overwrite."
        )

    # Parse existing values
    existing = dotenv_values(str(env_path))

    # Guard: refuse if already encrypted (has DOTENV_PUBLIC_KEY)
    if "DOTENV_PUBLIC_KEY" in existing:
        raise ValueError(
            f"File already has DOTENV_PUBLIC_KEY -- encryption already applied. "
            f"Remove DOTENV_PUBLIC_KEY to re-encrypt or use a fresh .env file."
        )

    # Generate secp256k1 key pair
    priv_bytes = os.urandom(32)
    key = PrivateKey(priv_bytes)
    pub_hex = key.public_key.format(compressed=True).hex()
    priv_hex = key.secret.hex()

    # Encrypt each plaintext value
    lines: list[str] = []
    for var_name, value in existing.items():
        if value is None:
            continue
        if value.startswith(ENCRYPTED_PREFIX):
            # Already encrypted -- preserve as-is
            lines.append(f'{var_name}="{value}"')
        else:
            cipher_bytes = ecies_encrypt(pub_hex, value.encode("utf-8"))
            enc_b64 = base64.b64encode(cipher_bytes).decode("ascii")
            lines.append(f'{var_name}="{ENCRYPTED_PREFIX}{enc_b64}"')

    # Write encrypted .env with header
    env_content = DOTENV_HEADER
    env_content += f'DOTENV_PUBLIC_KEY="{pub_hex}"\n'
    for line in lines:
        env_content += line + "\n"
    env_path.write_text(env_content)

    # Write .env.keys
    if env_name:
        suffix = _normalize_env_name(env_name)
        key_var = f"DOTENV_PRIVATE_KEY_{suffix}"
    else:
        key_var = "DOTENV_PRIVATE_KEY"

    keys_content = KEYS_HEADER
    keys_content += f'{key_var}="{priv_hex}"\n'
    keys_path.write_text(keys_content)
