"""Environment configuration parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

_VALID_ORIGINS = {"local", "gcp"}


@dataclass
class PrivateKeyConfig:
    """Configuration for how to resolve the private decryption key."""

    source: str                              # secret name to look up (e.g. "MY_CUSTOM_KEY")
    secret_origin: str = "local"             # 'local' or 'gcp'
    dotenv_path: Optional[str] = None        # for local: path to .env file containing the key
    gcp_project_id: Optional[str] = None     # for gcp: project ID


@dataclass
class EncryptedDotenvConfig:
    """Configuration for encrypted dotenv handling."""

    enabled: bool
    private_key: Optional[PrivateKeyConfig] = None


@dataclass
class EnvironmentConfig:
    """Parsed configuration for a single named environment."""

    name: str
    origin: str
    dotenv_path: Optional[str] = None
    gcp_project_id: Optional[str] = None
    is_default: bool = False
    encrypted_dotenv: Optional[EncryptedDotenvConfig] = None  # Phase 02 addition


def parse_environments(
    raw_config: dict[str, Any],
    project_root: Optional[str] = None,
) -> dict[str, EnvironmentConfig]:
    """Parse and validate the ``environments`` section of a YAML config.

    Parameters
    ----------
    raw_config:
        The full parsed YAML config dictionary.
    project_root:
        Optional project root for path resolution (reserved for future use).

    Returns
    -------
    dict[str, EnvironmentConfig]
        Mapping of environment name to its validated configuration.
        Empty dict when the config has no ``environments`` key.

    Raises
    ------
    ValueError
        When the environments section or an individual entry is invalid.
    """
    if "environments" not in raw_config:
        return {}

    environments = raw_config["environments"]

    if not isinstance(environments, dict):
        raise ValueError(
            "The 'environments' section must be a mapping, "
            f"got {type(environments).__name__}"
        )

    result: dict[str, EnvironmentConfig] = {}

    for env_name, env_data in environments.items():
        if not isinstance(env_data, dict):
            raise ValueError(
                f"Environment '{env_name}' must be a mapping, "
                f"got {type(env_data).__name__}"
            )

        # -- origin (required) ------------------------------------------------
        raw_origin = env_data.get("origin")
        if raw_origin is None:
            raise ValueError(
                f"Environment '{env_name}' is missing the required 'origin' field"
            )

        origin = str(raw_origin).lower()
        if origin not in _VALID_ORIGINS:
            raise ValueError(
                f"Environment '{env_name}' has invalid origin '{origin}'; "
                f"expected one of {sorted(_VALID_ORIGINS)}"
            )

        # -- origin-specific fields -------------------------------------------
        dotenv_path: Optional[str] = None
        gcp_project_id: Optional[str] = None

        if origin == "local":
            dotenv_path = env_data.get("dotenv_path", ".env")

        elif origin == "gcp":
            gcp_project_id = env_data.get("gcp_project_id")
            if gcp_project_id is None:
                raise ValueError(
                    f"Environment '{env_name}' with origin 'gcp' requires "
                    "'gcp_project_id'"
                )

        is_default = bool(env_data.get("default", False))

        # -- encrypted_dotenv (optional) --------------------------------------
        encrypted_dotenv: Optional[EncryptedDotenvConfig] = None
        raw_encrypted = env_data.get("encrypted_dotenv")
        if isinstance(raw_encrypted, dict) and raw_encrypted.get("enabled") is True:
            raw_pk = raw_encrypted.get("private_key")
            private_key_cfg: Optional[PrivateKeyConfig] = None
            if isinstance(raw_pk, dict):
                pk_source = raw_pk.get("source")
                if isinstance(pk_source, str) and pk_source.strip():
                    key_origin = raw_pk.get("secret_origin", "local")
                    if key_origin not in ("local", "gcp"):
                        key_origin = "local"
                    private_key_cfg = PrivateKeyConfig(
                        source=pk_source,
                        secret_origin=key_origin,
                        dotenv_path=raw_pk.get("dotenv_path"),
                        gcp_project_id=raw_pk.get("gcp_project_id"),
                    )
            encrypted_dotenv = EncryptedDotenvConfig(enabled=True, private_key=private_key_cfg)

        result[env_name] = EnvironmentConfig(
            name=env_name,
            origin=origin,
            dotenv_path=dotenv_path,
            gcp_project_id=gcp_project_id,
            is_default=is_default,
            encrypted_dotenv=encrypted_dotenv,
        )

    explicit_defaults = [name for name, cfg in result.items() if cfg.is_default]
    if len(explicit_defaults) > 1:
        raise ValueError(
            f"Only one environment may set 'default: true', "
            f"but found multiple: {explicit_defaults}"
        )

    return result
