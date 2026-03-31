"""Loader implementation for local .env files."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values, find_dotenv

from env_manager.base import SecretLoader
from env_manager.exceptions import DecryptionError, DecryptionIssue

try:
    from dev_utils.pretty_logger import PrettyLogger
except ImportError:  # pragma: no cover
    from env_manager.utils import PrettyLogger


logger = PrettyLogger("env-manager")

ENCRYPTED_PREFIX = "encrypted:"


class DotEnvLoader(SecretLoader):
    """Load secrets from a .env file and the current environment."""

    def __init__(
        self,
        dotenv_path: Optional[str] = None,
        *,
        encrypted: bool = False,
        environment_name: Optional[str] = None,
        explicit_private_key: Optional[str] = None,
    ) -> None:
        self._explicit_path = dotenv_path is not None
        self._dotenv_path = self._resolve_path(dotenv_path)
        self._values = self._load_dotenv_values()
        self._encrypted_enabled = encrypted
        self._environment_name = environment_name
        self._explicit_private_key = explicit_private_key
        self._resolved_private_key: Optional[str] = None  # lazy cache

    def _resolve_path(self, dotenv_path: Optional[str]) -> Optional[str]:
        if dotenv_path:
            return str(Path(dotenv_path).expanduser().resolve())
        discovered = find_dotenv(usecwd=True)
        if discovered:
            return discovered
        candidate = Path.cwd() / ".env"
        return str(candidate) if candidate.exists() else None

    def _load_dotenv_values(self) -> dict[str, str]:
        if not self._dotenv_path:
            return {}
        if not Path(self._dotenv_path).exists():
            return {}
        values = dotenv_values(self._dotenv_path)
        return {key: value for key, value in values.items() if value is not None}

    def _resolve_private_key(self) -> Optional[str]:
        """Resolve the private decryption key using the lookup chain.

        Order: explicit_private_key kwarg -> DOTENV_PRIVATE_KEY_<ENV> env var ->
        DOTENV_PRIVATE_KEY env var -> colocated .env.keys file.
        """
        # 0. Explicit kwarg overrides everything
        if self._explicit_private_key:
            return self._explicit_private_key

        # 1. Environment-specific key (only when environment_name is set)
        if self._environment_name:
            suffix = re.sub(r'[^A-Z0-9]+', '_', self._environment_name.upper())
            env_key = f"DOTENV_PRIVATE_KEY_{suffix}"
            if env_key in os.environ:
                return os.environ[env_key]

        # 2. Generic key
        if "DOTENV_PRIVATE_KEY" in os.environ:
            return os.environ["DOTENV_PRIVATE_KEY"]

        # 3. Colocated .env.keys file (relative to the dotenv file)
        if self._dotenv_path:
            keys_path = Path(self._dotenv_path).parent / ".env.keys"
            if keys_path.exists():
                kv = dotenv_values(str(keys_path))
                if "DOTENV_PRIVATE_KEY" in kv:
                    return kv["DOTENV_PRIVATE_KEY"]

        return None

    def _get_private_key(self) -> Optional[str]:
        """Return cached private key, resolving on first call."""
        if self._resolved_private_key is None:
            self._resolved_private_key = self._resolve_private_key()
        return self._resolved_private_key

    def _decrypt_value(self, key: str, raw_value: str) -> dict:
        """Attempt to decrypt a single encrypted: value.

        Returns dict with either {"value": str, "error": None} or
        {"value": None, "error": str}.
        """
        private_key = self._get_private_key()
        if not private_key:
            return {"error": f"No private key found to decrypt '{key}'", "value": None}

        cipher_b64 = raw_value[len(ENCRYPTED_PREFIX):]
        try:
            from ecies import decrypt as ecies_decrypt
        except ImportError:
            raise ImportError(
                "eciespy is required for encrypted dotenv support. "
                "Install it with: pip install env-manager[encrypted]"
            )

        try:
            cipher_bytes = base64.b64decode(cipher_b64)
            plaintext_bytes = ecies_decrypt(private_key, cipher_bytes)
            return {"value": plaintext_bytes.decode("utf-8"), "error": None}
        except Exception as exc:
            return {"error": f"Decryption failed for '{key}': {exc}", "value": None}

    def get(self, key: str) -> Optional[str]:
        self._ensure_file_backed_lookup_available([key])

        # os.environ always wins (unchanged behavior)
        env_val = os.environ.get(key)
        if env_val is not None:
            return env_val

        raw = self._values.get(key)
        if raw is None:
            return None

        if self._encrypted_enabled and raw.startswith(ENCRYPTED_PREFIX):
            result = self._decrypt_value(key, raw)
            if result["error"]:
                raise DecryptionError([DecryptionIssue(key=key, message=result["error"])])
            return result["value"]

        return raw

    def get_many(self, keys: list[str]) -> dict[str, Optional[str]]:
        self._ensure_file_backed_lookup_available(keys)

        if not self._encrypted_enabled:
            return {key: self.get(key) for key in keys}

        result: dict[str, Optional[str]] = {}
        issues: list[DecryptionIssue] = []

        for key in keys:
            # os.environ always wins
            env_val = os.environ.get(key)
            if env_val is not None:
                result[key] = env_val
                continue

            raw = self._values.get(key)
            if raw is None:
                result[key] = None
                continue

            if raw.startswith(ENCRYPTED_PREFIX):
                outcome = self._decrypt_value(key, raw)
                if outcome["error"]:
                    issues.append(DecryptionIssue(key=key, message=outcome["error"]))
                    result[key] = None
                else:
                    result[key] = outcome["value"]
            else:
                result[key] = raw

        if issues:
            raise DecryptionError(issues)

        return result

    def _ensure_file_backed_lookup_available(self, keys: list[str]) -> None:
        if not self._explicit_path or not self._dotenv_path:
            return

        if Path(self._dotenv_path).exists():
            return

        unresolved = [key for key in keys if key not in os.environ]
        if unresolved:
            raise FileNotFoundError(self._dotenv_path)

    @property
    def dotenv_path(self) -> Optional[str]:
        """Return the resolved path to the .env file, if any."""

        return self._dotenv_path
