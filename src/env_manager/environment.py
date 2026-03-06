"""Environment configuration parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

_VALID_ORIGINS = {"local", "gcp"}


@dataclass
class EnvironmentConfig:
    """Parsed configuration for a single named environment."""

    name: str
    origin: str
    dotenv_path: Optional[str] = None
    gcp_project_id: Optional[str] = None


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

        result[env_name] = EnvironmentConfig(
            name=env_name,
            origin=origin,
            dotenv_path=dotenv_path,
            gcp_project_id=gcp_project_id,
        )

    return result
