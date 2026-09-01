"""Decrypt a dotenvx-compatible encrypted .env file back to plaintext.

Paridad con `env-manager decrypt` del runtime JS: mismos flags, mismos
mensajes, mismos exit codes.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

ENCRYPTED_PREFIX = "encrypted:"


def _normalize_env_name(name: str) -> str:
    """Normalize an environment name to the .env.keys suffix form."""

    return re.sub(r"[^A-Z0-9]+", "_", name.upper())


def _load_private_key_from_keys_file(
    env_file_path: Path, env_name: Optional[str]
) -> str:
    keys_path = env_file_path.parent / ".env.keys"
    if not keys_path.exists():
        raise FileNotFoundError(
            f".env.keys not found at {keys_path}. Provide a key with --key."
        )

    parsed = dotenv_values(str(keys_path))

    if env_name:
        var_name = f"DOTENV_PRIVATE_KEY_{_normalize_env_name(env_name)}"
        key = parsed.get(var_name)
        if not key:
            raise ValueError(f"{var_name} not found in .env.keys")
        return key

    key = parsed.get("DOTENV_PRIVATE_KEY")
    if not key:
        raise ValueError("DOTENV_PRIVATE_KEY not found in .env.keys")
    return key


def decrypt_dotenv_file(
    file_path: str,
    *,
    private_key_hex: Optional[str] = None,
    output_path: Optional[str] = None,
    env_name: Optional[str] = None,
) -> tuple[int, int]:
    """Decrypt every ``encrypted:`` value in ``file_path``.

    Devuelve ``(descifrados, omitidos)``. Quita del resultado la línea
    ``DOTENV_PUBLIC_KEY`` y la cabecera de dotenvx: el archivo resultante es
    texto plano otra vez.
    """

    # Primero lo que no depende de extras: si el archivo no está, el error es
    # el mismo tenga o no instalado eciespy. Así el exit code es estable entre
    # entornos y entre runtimes.
    env_path = Path(file_path)
    if not env_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        from ecies import decrypt as ecies_decrypt
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ImportError(
            "eciespy is required for the decrypt command. "
            "Install it with: pip install notoriosti-env-manager[encrypted]"
        ) from exc

    parsed = dotenv_values(str(env_path))

    key_hex = private_key_hex or _load_private_key_from_keys_file(env_path, env_name)
    key_bytes = bytes.fromhex(key_hex)

    decrypted_count = 0
    skipped_count = 0
    entries: dict[str, str] = {}

    for name, value in parsed.items():
        if name == "DOTENV_PUBLIC_KEY":
            # Ya no sirve una vez descifrado el archivo.
            continue
        if value is None:
            continue
        if value.startswith(ENCRYPTED_PREFIX):
            cipher = base64.b64decode(value[len(ENCRYPTED_PREFIX) :])
            entries[name] = ecies_decrypt(key_bytes, cipher).decode("utf-8")
            decrypted_count += 1
        else:
            entries[name] = value
            skipped_count += 1

    out_path = Path(output_path) if output_path else env_path
    body = "".join(f'{name}="{value}"\n' for name, value in entries.items())
    out_path.write_text(body)

    return decrypted_count, skipped_count
