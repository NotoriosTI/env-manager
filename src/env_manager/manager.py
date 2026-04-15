"""High-level configuration manager for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import dotenv_values, find_dotenv

from env_manager.environment import EncryptedDotenvConfig, EnvironmentConfig, PrivateKeyConfig, parse_environments
from env_manager.factory import create_loader
from env_manager.utils import coerce_type, load_yaml, logger, mask_secret

from .base import SecretLoader

_VALID_ORIGINS = {"local", "gcp"}


@dataclass(frozen=True)
class SourceContext:
    """Effective source settings for one variable lookup."""

    environment_name: str
    origin: str
    dotenv_path: Optional[str]
    gcp_project_id: Optional[str]


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
        self._project_root = self._discover_project_root()
        self._raw_config = load_yaml(str(self._config_path))
        self._variables = self._extract_variables()
        self._validation = self._extract_validation()

        # Parse environments and select active one BEFORE resolving origin/dotenv/gcp
        self._environments = parse_environments(
            self._raw_config,
            project_root=str(self._project_root),
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
        self._loaders: dict[tuple[str, Optional[str], Optional[str], Optional[str]], SecretLoader] = {}
        self._values: dict[str, Any] = {}
        self._loaded = False
        self._encrypted_enabled: bool = False

        if auto_load:
            self.load()

    def _resolve_dotenv_path(self, provided: Optional[str]) -> Optional[str]:
        if provided:
            self._has_explicit_dotenv_contract = True
            return self._resolve_project_path(provided)
        # Check active environment config before standard discovery
        if self._active_environment and self._active_environment.dotenv_path:
            self._has_explicit_dotenv_contract = True
            return self._resolve_project_path(self._active_environment.dotenv_path)
        discovered = find_dotenv(usecwd=True)
        if discovered:
            return discovered
        fallback = self._project_root / ".env"
        return str(fallback) if fallback.exists() else None

    def _discover_project_root(self) -> Path:
        current = self._config_path.parent
        git_root: Optional[Path] = None
        for candidate in (current, *current.parents):
            if (candidate / "pyproject.toml").exists():
                return candidate
            # Record the innermost git root we cross
            if git_root is None and (candidate / ".git").exists():
                git_root = candidate
                break  # Don't climb past git boundaries
        return git_root if git_root is not None else self._config_path.parent

    def _resolve_project_path(self, raw_path: str) -> str:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return str(candidate.resolve())
        return str((self._project_root / candidate).resolve())

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
        """Select the active environment based on the APP_ENV env var.

        Returns None when no environments are defined or when APP_ENV is
        unset and there is no ``default`` environment (deferred error).
        """
        if not self._environments:
            return None

        env_name = os.environ.get("APP_ENV")
        if env_name is not None:
            if env_name not in self._environments:
                available = sorted(self._environments.keys())
                raise ValueError(
                    f"APP_ENV='{env_name}' is not defined in the config. "
                    f"Available environments: {available}"
                )
            return self._environments[env_name]

        # APP_ENV not set -- fall back to "default" if it exists
        # Explicit default: true marker takes precedence over key name
        explicit_defaults = [e for e in self._environments.values() if e.is_default]
        if explicit_defaults:
            return explicit_defaults[0]  # parse_environments guarantees at most one

        # Fall back to environment literally named "default"
        return self._environments.get("default")

    @property
    def active_environment(self) -> Optional[EnvironmentConfig]:
        """Return the active environment configuration, if any."""
        return self._active_environment

    def _ensure_loader(self) -> SecretLoader:
        if self._loader is None:
            self._loader = self._get_loader_for_context(self._default_source_context())
        return self._loader

    def _get_loader_for_context(self, context: SourceContext) -> SecretLoader:
        cache_key = (context.origin, context.gcp_project_id, context.dotenv_path, context.environment_name)
        loader = self._loaders.get(cache_key)
        if loader is None:
            # Guard: GCP + encrypted is not supported
            if self._encrypted_enabled and context.origin == "gcp":
                raise NotImplementedError(
                    "Encrypted dotenv loading from non-local origins is not yet supported. "
                    "See Backlog 999.1."
                )
            _, explicit_private_key = self._resolve_encrypted_dotenv_config()
            loader = create_loader(
                context.origin,
                gcp_project_id=context.gcp_project_id,
                dotenv_path=context.dotenv_path,
                encrypted=self._encrypted_enabled,
                environment_name=context.environment_name,
                explicit_private_key=explicit_private_key,
            )
            self._loaders[cache_key] = loader
        return loader

    def _default_source_context(self) -> SourceContext:
        return SourceContext(
            environment_name=(
                self._active_environment.name if self._active_environment else "default"
            ),
            origin=self.secret_origin,
            dotenv_path=self._dotenv_path,
            gcp_project_id=self.gcp_project_id,
        )

    def _resolve_encrypted_dotenv_config(self) -> tuple[bool, Optional[str]]:
        """Determine if encrypted dotenv is enabled and resolve the explicit private key.

        Returns (encrypted_enabled, explicit_private_key).
        For new-format configs: reads from active environment's encrypted_dotenv block.
        For old-format configs: reads from top-level encrypted_dotenv block.
        """
        # New-format: per-environment encrypted_dotenv
        if self._active_environment and self._active_environment.encrypted_dotenv:
            enc_cfg = self._active_environment.encrypted_dotenv
            if enc_cfg.enabled:
                explicit_key = None
                if enc_cfg.private_key:
                    pk_cfg = enc_cfg.private_key
                    if pk_cfg.secret_origin == "gcp":
                        raise NotImplementedError(
                            "Encrypted dotenv loading from non-local origins is not yet supported. "
                            "See Backlog 999.1."
                        )
                    # Local key resolution: look up pk_cfg.source as env var or from dotenv file
                    explicit_key = os.environ.get(pk_cfg.source)
                    if explicit_key is None and pk_cfg.dotenv_path:
                        from dotenv import dotenv_values
                        resolved_pk_path = self._resolve_project_path(pk_cfg.dotenv_path)
                        kv = dotenv_values(resolved_pk_path)
                        explicit_key = kv.get(pk_cfg.source)
                return (True, explicit_key)
            return (False, None)

        # Old-format: top-level encrypted_dotenv
        raw_enc = self._raw_config.get("encrypted_dotenv")
        if isinstance(raw_enc, dict) and raw_enc.get("enabled") is True:
            return (True, None)

        return (False, None)

    def _resolve_environment_dotenv_path(
        self, environment: EnvironmentConfig
    ) -> Optional[str]:
        if not environment.dotenv_path:
            return None
        return self._resolve_project_path(environment.dotenv_path)

    def _environment_source_context(self, environment: EnvironmentConfig) -> SourceContext:
        return SourceContext(
            environment_name=environment.name,
            origin=environment.origin,
            dotenv_path=self._resolve_environment_dotenv_path(environment),
            gcp_project_id=environment.gcp_project_id,
        )

    def _effective_source_context(
        self, var_name: str, definition: dict[str, Any]
    ) -> SourceContext:
        environment_name = definition.get("environment")
        origin_override = definition.get("origin")

        context = self._default_source_context()
        if environment_name:
            context = self._environment_source_context(self._environments[environment_name])

        if origin_override:
            origin = str(origin_override).strip().lower()
            dotenv_path = context.dotenv_path
            if origin == "gcp":
                dotenv_path = None
            elif dotenv_path is None:
                dotenv_path = self._dotenv_path
            context = SourceContext(
                environment_name=context.environment_name,
                origin=origin,
                dotenv_path=dotenv_path,
                gcp_project_id=context.gcp_project_id,
            )

        dotenv_override = definition.get("dotenv_path")
        if dotenv_override is not None:
            if not isinstance(dotenv_override, str) or not dotenv_override.strip():
                raise ValueError(
                    f"Variable '{var_name}': 'dotenv_path' must be a non-empty string."
                )
            context = SourceContext(
                environment_name=context.environment_name,
                origin=context.origin,
                dotenv_path=self._resolve_project_path(dotenv_override),
                gcp_project_id=context.gcp_project_id,
            )

        return context

    def load(self) -> None:
        """Load variables according to the YAML configuration."""

        if self._loaded:
            return

        self._loaders = {}  # Reset loader cache for retry safety (Phase 01 pattern)
        encrypted_enabled, _ = self._resolve_encrypted_dotenv_config()
        self._encrypted_enabled = encrypted_enabled
        # explicit_private_key is resolved fresh in _get_loader_for_context() — not cached here

        sources = {}
        contexts: dict[str, SourceContext] = {}
        default_only_variables: list[str] = []
        sourced_variables: list[str] = []
        for name, definition in self._variables.items():
            source = self._validate_variable_definition(name, definition)
            sources[name] = source
            if source is None:
                default_only_variables.append(name)
            else:
                sourced_variables.append(name)
                contexts[name] = self._effective_source_context(name, definition)

        fetched: dict[str, Optional[str]] = {}
        variables_needing_lookup: dict[
            tuple[str, Optional[str], Optional[str], str], list[str]
        ] = {}
        for name in sourced_variables:
            if name in os.environ:
                fetched[sources[name]] = os.environ[name]
                continue
            context = contexts[name]
            group_key = (
                context.origin,
                context.gcp_project_id,
                context.dotenv_path,
                context.environment_name,
            )
            variables_needing_lookup.setdefault(group_key, []).append(name)

        for grouped_names in variables_needing_lookup.values():
            sample_name = grouped_names[0]
            context = contexts[sample_name]
            loader = self._get_loader_for_context(context)
            try:
                fetched.update(
                    loader.get_many([sources[name] for name in grouped_names])
                )
            except FileNotFoundError as exc:
                missing_path = Path(str(exc)).expanduser().resolve()
                missing_variables = ", ".join(grouped_names)
                raise RuntimeError(
                    "Variable(s) %s in %s require local .env file '%s' for sourced lookups."
                    % (missing_variables, self._format_environment_label(context), missing_path)
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
                    message = self._format_strict_missing_message(
                        var_name, source, contexts[var_name]
                    )
                    logger.error(message)
                    raise RuntimeError(message)
                if has_default:
                    if var_name in required:
                        logger.warning(
                            self._format_default_fallback_warning(
                                var_name, source, contexts[var_name]
                            )
                        )
                    raw_value = default_value
                else:
                    if var_name in required:
                        message = self._format_required_missing_message(
                            var_name, source, contexts[var_name]
                        )
                        logger.error(message)
                        raise RuntimeError(message)
                    if var_name in optional:
                        logger.warning(
                            self._format_optional_missing_warning(
                                var_name, source, contexts[var_name]
                            )
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

        environment_name = definition.get("environment")
        if environment_name is not None:
            if not isinstance(environment_name, str) or not environment_name.strip():
                raise ValueError(
                    f"Variable '{name}': 'environment' must be a non-empty string."
                )
            if environment_name not in self._environments:
                available = sorted(self._environments.keys())
                raise ValueError(
                    f"Variable '{name}' references undefined environment "
                    f"'{environment_name}'. Available environments: {available}"
                )

        origin_override = definition.get("origin")
        if origin_override is not None:
            if not isinstance(origin_override, str) or not origin_override.strip():
                raise ValueError(
                    f"Variable '{name}': 'origin' must be a non-empty string."
                )
            normalized_origin = origin_override.strip().lower()
            if normalized_origin not in _VALID_ORIGINS:
                raise ValueError(
                    f"Variable '{name}' has invalid origin '{origin_override}'; "
                    f"expected one of {sorted(_VALID_ORIGINS)}"
                )

        dotenv_path_override = definition.get("dotenv_path")
        if dotenv_path_override is not None:
            if not isinstance(dotenv_path_override, str) or not dotenv_path_override.strip():
                raise ValueError(
                    f"Variable '{name}': 'dotenv_path' must be a non-empty string."
                )
        
        v_type = str(definition.get("type", "str"))
        if v_type not in {"str", "int", "float", "bool"}:
            raise ValueError(
                f"Variable '{name}' uses unsupported type '{v_type}'."
            )
        return source

    def _format_environment_label(
        self, context: Optional[SourceContext] = None
    ) -> str:
        environment_name = (
            context.environment_name
            if context is not None
            else (
                self._active_environment.name if self._active_environment else "default"
            )
        )
        return f"environment '{environment_name}'"

    def _format_runtime_context(self, context: Optional[SourceContext] = None) -> str:
        effective_context = context or self._default_source_context()
        if effective_context.origin == "gcp":
            project_id = effective_context.gcp_project_id or "unknown-project"
            return (
                f"{self._format_environment_label(effective_context)} "
                f"using GCP project '{project_id}'"
            )

        dotenv_path = effective_context.dotenv_path or "<no dotenv file>"
        return (
            f"{self._format_environment_label(effective_context)} "
            f"using local .env '{dotenv_path}'"
        )

    def _format_required_missing_message(
        self, var_name: str, source: str, context: Optional[SourceContext] = None
    ) -> str:
        return (
            f"Required variable '{var_name}' not found in source '{source}' for "
            f"{self._format_runtime_context(context)}."
        )

    def _format_default_fallback_warning(
        self, var_name: str, source: str, context: Optional[SourceContext] = None
    ) -> str:
        return (
            f"Required variable '{var_name}' missing from source; using YAML default "
            f"for source '{source}' in {self._format_runtime_context(context)}."
        )

    def _format_optional_missing_warning(
        self, var_name: str, source: str, context: Optional[SourceContext] = None
    ) -> str:
        return (
            f"Optional variable '{var_name}' resolved to None because source "
            f"'{source}' was unavailable in {self._format_runtime_context(context)}."
        )

    def _format_strict_missing_message(
        self, var_name: str, source: str, context: Optional[SourceContext] = None
    ) -> str:
        return (
            f"Strict mode: variable '{var_name}' is missing from source '{source}' in "
            f"{self._format_runtime_context(context)}."
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
