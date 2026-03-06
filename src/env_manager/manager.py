"""High-level configuration manager for secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import dotenv_values, find_dotenv

from env_manager.environment import EnvironmentConfig, parse_environments
from env_manager.factory import create_loader
from env_manager.utils import coerce_type, load_yaml, logger, mask_secret

from .base import SecretLoader


class ConfigManager:
    """Load and validate configuration variables from multiple sources."""

    def __init__(
        self,
        config_path: str,
        *,
        secret_origin: Optional[str] = None,
        gcp_project_id: Optional[str] = None,
        strict: Optional[bool] = None,
        auto_load: bool = True,
        dotenv_path: Optional[str] = None,
        debug: bool = False,
    ) -> None:
        self._config_path = Path(config_path).expanduser().resolve()
        self._raw_config = load_yaml(str(self._config_path))
        self._variables = self._extract_variables()
        self._validation = self._extract_validation()

        # Parse environments and select active one BEFORE resolving origin/dotenv/gcp
        self._environments = parse_environments(
            self._raw_config,
            project_root=str(self._config_path.parent),
        )
        self._active_environment = self._select_environment()

        self._has_explicit_dotenv_contract = False
        self._dotenv_path = self._resolve_dotenv_path(dotenv_path)
        self._dotenv_values = self._read_dotenv_values()
        self._debug = debug

        self.secret_origin = self._resolve_secret_origin(secret_origin)
        self.gcp_project_id = self._resolve_gcp_project_id(gcp_project_id)
        self.strict = self._resolve_strict(strict)

        self._loader: Optional[SecretLoader] = None
        self._values: dict[str, Any] = {}
        self._loaded = False

        if auto_load:
            self.load()

    def _resolve_dotenv_path(self, provided: Optional[str]) -> Optional[str]:
        if provided:
            self._has_explicit_dotenv_contract = True
            candidate = Path(provided).expanduser()
            return str(candidate.resolve())
        # Check active environment config before standard discovery
        if self._active_environment and self._active_environment.dotenv_path:
            self._has_explicit_dotenv_contract = True
            env_dotenv = Path(self._config_path.parent) / self._active_environment.dotenv_path
            return str(env_dotenv.resolve())
        discovered = find_dotenv(usecwd=True)
        if discovered:
            return discovered
        fallback = self._config_path.parent / ".env"
        return str(fallback) if fallback.exists() else None

    def _read_dotenv_values(self) -> dict[str, str]:
        if not self._dotenv_path:
            return {}
        if not Path(self._dotenv_path).exists():
            return {}
        values = dotenv_values(self._dotenv_path)
        return {key: value for key, value in values.items() if value is not None}

    def _resolve_secret_origin(self, provided: Optional[str]) -> str:
        # Priority order:
        # 1. Explicitly provided parameter
        # 2. Environment variable
        # 3. Value from .env file (read without loading entire file)
        # 4. Active environment config origin
        # 5. Default: "local"
        if provided:
            return provided.strip().lower()

        # Check os.environ first
        env_origin = os.environ.get("SECRET_ORIGIN")
        if env_origin:
            return env_origin.strip().lower()

        # Check .env file without loading entire file to os.environ
        if self._dotenv_values:
            dotenv_origin = self._dotenv_values.get("SECRET_ORIGIN")
            if dotenv_origin:
                return dotenv_origin.strip().lower()

        # Check active environment config
        if self._active_environment:
            return self._active_environment.origin

        return "local"

    def _resolve_gcp_project_id(self, provided: Optional[str]) -> Optional[str]:
        # Priority order:
        # 1. Explicitly provided parameter
        # 2. Environment variable
        # 3. Value from .env file
        # 4. Active environment config gcp_project_id
        # 5. Not set
        candidate = (
            provided
            or os.environ.get("GCP_PROJECT_ID")
            or self._dotenv_values.get("GCP_PROJECT_ID")
        )
        if candidate:
            os.environ.setdefault("GCP_PROJECT_ID", candidate)
            return candidate

        # Check active environment config
        if self._active_environment and self._active_environment.gcp_project_id:
            gcp_id = self._active_environment.gcp_project_id
            os.environ.setdefault("GCP_PROJECT_ID", gcp_id)
            return gcp_id

        logger.warning("GCP_PROJECT_ID not set. Some features may not work.")
        return None

    def _resolve_strict(self, provided: Optional[bool]) -> bool:
        if provided is not None:
            return provided
        return bool(self._validation.get("strict", False))

    def _extract_variables(self) -> dict[str, dict[str, Any]]:
        variables = self._raw_config.get("variables", {})
        if not isinstance(variables, dict):
            raise ValueError(
                "'variables' section in config must be a mapping of variable definitions."
            )
        return variables

    def _extract_validation(self) -> dict[str, Any]:
        validation = self._raw_config.get("validation", {})
        if validation and not isinstance(validation, dict):
            raise ValueError("'validation' section must be a mapping if provided.")
        data = validation or {}
        for key in ("required", "optional"):
            collection = data.get(key)
            if collection is None:
                continue
            if not isinstance(collection, list):
                raise ValueError(
                    f"Validation '{key}' entry must be a list if provided."
                )
        return data

    def _select_environment(self) -> Optional[EnvironmentConfig]:
        """Select the active environment based on the ENVIRONMENT env var.

        Returns None when no environments are defined or when ENVIRONMENT is
        unset and there is no ``default`` environment (deferred error).
        """
        if not self._environments:
            return None

        env_name = os.environ.get("ENVIRONMENT")
        if env_name is not None:
            if env_name not in self._environments:
                available = sorted(self._environments.keys())
                raise ValueError(
                    f"Environment '{env_name}' is not defined in the config. "
                    f"Available environments: {available}"
                )
            return self._environments[env_name]

        # ENVIRONMENT not set -- fall back to "default" if it exists
        return self._environments.get("default")

    @property
    def active_environment(self) -> Optional[EnvironmentConfig]:
        """Return the active environment configuration, if any."""
        return self._active_environment

    def _ensure_loader(self) -> SecretLoader:
        if self._loader is None:
            self._loader = create_loader(
                self.secret_origin,
                gcp_project_id=self.gcp_project_id,
                dotenv_path=self._dotenv_path,
            )
        return self._loader

    def load(self) -> None:
        """Load variables according to the YAML configuration."""

        if self._loaded:
            return

        sources = {}
        default_only_variables: list[str] = []
        sourced_variables: list[str] = []
        for name, definition in self._variables.items():
            source = self._validate_variable_definition(name, definition)
            sources[name] = source
            if source is None:
                default_only_variables.append(name)
            else:
                sourced_variables.append(name)

        fetched: dict[str, Optional[str]] = {}
        if sourced_variables:
            loader = self._ensure_loader()
            try:
                fetched = loader.get_many([sources[name] for name in sourced_variables])
            except FileNotFoundError as exc:
                missing_path = Path(str(exc)).expanduser().resolve()
                raise RuntimeError(
                    "Active %s requires local .env file '%s' for sourced lookups."
                    % (self._format_environment_label(), missing_path)
                ) from exc

        required = set(self._validation.get("required", []) or [])
        optional = set(self._validation.get("optional", []) or [])

        for var_name in default_only_variables:
            definition = self._variables[var_name]
            target_type = str(definition.get("type", "str"))
            raw_value = definition["default"]
            self._store_loaded_value(var_name, raw_value, target_type)

        for var_name in sourced_variables:
            definition = self._variables[var_name]
            source = sources[var_name]
            target_type = str(definition.get("type", "str"))
            has_default = "default" in definition
            default_value = definition.get("default") if has_default else None
            raw_value = fetched.get(source)

            if raw_value is None:
                if self.strict:
                    message = self._format_strict_missing_message(var_name, source)
                    logger.error(message)
                    raise RuntimeError(message)
                if has_default:
                    if var_name in required:
                        logger.warning(
                            self._format_default_fallback_warning(var_name, source)
                        )
                    raw_value = default_value
                else:
                    if var_name in required:
                        message = self._format_required_missing_message(var_name, source)
                        logger.error(message)
                        raise RuntimeError(message)
                    if var_name in optional:
                        logger.warning(
                            self._format_optional_missing_warning(var_name, source)
                        )
                    self._values[var_name] = None
                    continue

            self._store_loaded_value(var_name, raw_value, target_type)

        self._loaded = True

    def _store_loaded_value(self, var_name: str, raw_value: Any, target_type: str) -> None:
        try:
            coerced_value = coerce_type(raw_value, target_type, var_name)
        except ValueError as exc:
            logger.error(f"Type coercion failed for {var_name}: {exc}")
            raise
        self._values[var_name] = coerced_value
        os.environ[var_name] = str(coerced_value)
        display_value = (
            str(coerced_value) if self._debug else mask_secret(str(coerced_value))
        )
        logger.info(f"Loaded {var_name}: {display_value}")

    def _validate_variable_definition(
        self, name: str, definition: Any
    ) -> Optional[str]:
        if not isinstance(definition, dict):
            raise ValueError(
                f"Invalid configuration for '{name}'. Expected a mapping."
            )
        
        source = definition.get("source")
        has_default = "default" in definition
        
        # Either source or default must be present, but not necessarily both
        if not source and not has_default:
            raise ValueError(
                f"Variable '{name}' must define either 'source' or 'default' (or both)."
            )
        
        # If source is present, it must be a non-empty string
        if source and not isinstance(source, str):
            raise ValueError(
                f"Variable '{name}': 'source' must be a string if provided."
            )
        
        v_type = str(definition.get("type", "str"))
        if v_type not in {"str", "int", "float", "bool"}:
            raise ValueError(
                f"Variable '{name}' uses unsupported type '{v_type}'."
            )
        return source

    def _format_environment_label(self) -> str:
        environment_name = (
            self._active_environment.name if self._active_environment else "default"
        )
        return f"environment '{environment_name}'"

    def _format_runtime_context(self) -> str:
        if self.secret_origin == "gcp":
            project_id = self.gcp_project_id or "unknown-project"
            return (
                f"{self._format_environment_label()} using GCP project '{project_id}'"
            )

        dotenv_path = self._dotenv_path or "<no dotenv file>"
        return (
            f"{self._format_environment_label()} using local .env '{dotenv_path}'"
        )

    def _format_required_missing_message(self, var_name: str, source: str) -> str:
        return (
            f"Required variable '{var_name}' not found in source '{source}' for "
            f"{self._format_runtime_context()}."
        )

    def _format_default_fallback_warning(self, var_name: str, source: str) -> str:
        return (
            f"Required variable '{var_name}' missing from source; using YAML default "
            f"for source '{source}' in {self._format_runtime_context()}."
        )

    def _format_optional_missing_warning(self, var_name: str, source: str) -> str:
        return (
            f"Optional variable '{var_name}' resolved to None because source "
            f"'{source}' was unavailable in {self._format_runtime_context()}."
        )

    def _format_strict_missing_message(self, var_name: str, source: str) -> str:
        return (
            f"Strict mode: variable '{var_name}' is missing from source '{source}' in "
            f"{self._format_runtime_context()}."
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key`` if present, else ``default``."""

        if not self._loaded:
            self.load()
        return self._values.get(key, default)

    def require(self, key: str) -> Any:
        """Return the value for ``key`` or raise if missing."""

        if not self._loaded:
            self.load()
        if key not in self._values or self._values[key] is None:
            raise RuntimeError(
                f"Required configuration '{key}' is missing. "
                "Call init_config or set a default."
            )
        return self._values[key]

    @property
    def values(self) -> dict[str, Any]:
        """Return a copy of loaded values."""

        if not self._loaded:
            self.load()
        return dict(self._values)


_SINGLETON: Optional[ConfigManager] = None


def init_config(
    config_path: str,
    *,
    secret_origin: Optional[str] = None,
    gcp_project_id: Optional[str] = None,
    strict: Optional[bool] = None,
    auto_load: bool = True,
    dotenv_path: Optional[str] = None,
    debug: bool = False,
) -> ConfigManager:
    """Initialise the global configuration manager singleton."""

    global _SINGLETON
    if _SINGLETON is not None:
        logger.warning(
            "Configuration manager already initialised. Replacing existing instance."
        )
    _SINGLETON = ConfigManager(
        config_path,
        secret_origin=secret_origin,
        gcp_project_id=gcp_project_id,
        strict=strict,
        auto_load=auto_load,
        dotenv_path=dotenv_path,
        debug=debug,
    )
    return _SINGLETON


def get_config(key: str, default: Any = None) -> Any:
    """Retrieve a configuration value from the singleton manager."""

    if _SINGLETON is None:
        raise RuntimeError("Configuration manager not initialised. Call init_config().")
    return _SINGLETON.get(key, default)


def require_config(key: str) -> Any:
    """Retrieve a mandatory configuration value.

    Raises an error if the configuration manager is not initialised or the value is
    missing.
    """

    if _SINGLETON is None:
        raise RuntimeError("Configuration manager not initialised. Call init_config().")
    return _SINGLETON.require(key)
