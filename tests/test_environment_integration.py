"""Integration tests for environment selection and backwards compatibility."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager, get_config, init_config, require_config
from conftest import write_config, write_env


# ===========================================================================
# New-format YAML with environments section
# ===========================================================================


class TestEnvironmentSelection:
    """ENVIRONMENT env var selects the correct named environment."""

    YAML_WITH_ENVS = """\
    environments:
      default:
        origin: local
        dotenv_path: .env
      staging:
        origin: local
        dotenv_path: .env.staging
      production:
        origin: gcp
        gcp_project_id: my-prod-project
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
    """

    def test_environment_var_selects_staging(self, tmp_path, monkeypatch):
        """ENVIRONMENT=staging selects staging config."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        staging_env = tmp_path / ".env.staging"
        staging_env.write_text("DB_PASSWORD=staging_secret\n", encoding="utf-8")

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is not None
        assert mgr.active_environment.name == "staging"
        assert mgr.active_environment.origin == "local"
        assert mgr.active_environment.dotenv_path == ".env.staging"

    def test_environment_unset_falls_back_to_default(self, tmp_path, monkeypatch):
        """Omitting ENVIRONMENT falls back to default environment."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is not None
        assert mgr.active_environment.name == "default"

    def test_undefined_environment_raises_value_error(self, tmp_path, monkeypatch):
        """ENVIRONMENT=unknown raises ValueError with descriptive message."""
        monkeypatch.setenv("ENVIRONMENT", "unknown")
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)

        with pytest.raises(ValueError, match="unknown"):
            ConfigManager(str(config_path), auto_load=False)

    def test_undefined_environment_error_lists_available(self, tmp_path, monkeypatch):
        """Error message lists available environment names."""
        monkeypatch.setenv("ENVIRONMENT", "typo")
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)

        with pytest.raises(ValueError) as exc_info:
            ConfigManager(str(config_path), auto_load=False)

        msg = str(exc_info.value)
        assert "default" in msg
        assert "staging" in msg
        assert "production" in msg

    def test_environment_origin_used_for_secret_origin(self, tmp_path, monkeypatch):
        """Active environment's origin is used as secret_origin."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.secret_origin == "local"

    def test_environment_gcp_project_id_used(self, tmp_path, monkeypatch):
        """Active environment's gcp_project_id is propagated."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        # Change cwd so find_dotenv doesn't discover the project's real .env
        monkeypatch.chdir(tmp_path)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.gcp_project_id == "my-prod-project"

    def test_variable_environment_uses_pinned_environment_context(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.chdir(tmp_path)
        config_path = write_config(
            tmp_path,
            """
            environments:
              default:
                origin: local
                dotenv_path: .env
              staging:
                origin: local
                dotenv_path: .env.staging
              production:
                origin: gcp
                gcp_project_id: prod-project
            variables:
              SHARED_TOKEN:
                source: shared/token
              PROD_TOKEN:
                source: prod/token
                environment: production
            """,
        )

        calls: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []

        class FakeLoader:
            def __init__(self, values):
                self._values = values

            def get_many(self, keys):
                requested = tuple(keys)
                calls.append(requested)
                return {key: self._values.get(key) for key in keys}

        def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None, **kwargs):
            context = (origin, gcp_project_id, dotenv_path)
            if origin == "local":
                assert dotenv_path == str((tmp_path / ".env.staging").resolve())
                return FakeLoader({"shared/token": "staging-value"})
            assert origin == "gcp"
            assert gcp_project_id == "prod-project"
            return FakeLoader({"prod/token": "prod-value"})

        monkeypatch.setattr(manager_module, "create_loader", fake_create_loader)

        manager = ConfigManager(str(config_path), auto_load=True)

        assert manager.get("SHARED_TOKEN") == "staging-value"
        assert manager.get("PROD_TOKEN") == "prod-value"
        assert calls == [("shared/token",), ("prod/token",)]

    def test_variable_origin_override_replaces_only_origin_on_pinned_environment(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.chdir(tmp_path)
        config_path = write_config(
            tmp_path,
            """
            environments:
              staging:
                origin: local
                dotenv_path: .env.staging
              production:
                origin: gcp
                gcp_project_id: prod-project
            variables:
              PROD_LOCAL_TOKEN:
                source: PROD_LOCAL_TOKEN
                environment: production
                origin: local
            """,
        )
        (tmp_path / ".env.staging").write_text("PROD_LOCAL_TOKEN=wrong\n", encoding="utf-8")
        prod_env = tmp_path / ".env.production"
        prod_env.write_text("PROD_LOCAL_TOKEN=from-prod-local\n", encoding="utf-8")

        observed: list[tuple[str, str | None, str | None]] = []
        original_create_loader = manager_module.create_loader

        def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None, **kwargs):
            observed.append((origin, gcp_project_id, dotenv_path))
            return original_create_loader(
                origin,
                gcp_project_id=gcp_project_id,
                dotenv_path=dotenv_path,
            )

        monkeypatch.setattr(manager_module, "create_loader", fake_create_loader)

        manager = ConfigManager(
            str(config_path),
            dotenv_path=str(prod_env),
            auto_load=True,
        )

        assert manager.get("PROD_LOCAL_TOKEN") == "from-prod-local"
        assert observed == [("local", "prod-project", str(prod_env.resolve()))]

    def test_variable_override_validation_rejects_unknown_environment(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_TOKEN", "from-os")
        config_path = write_config(
            tmp_path,
            """
            environments:
              default:
                origin: local
                dotenv_path: .env
              production:
                origin: gcp
                gcp_project_id: prod-project
            variables:
              API_TOKEN:
                source: API_TOKEN
                environment: typo
            """,
        )

        with pytest.raises(ValueError) as exc_info:
            ConfigManager(str(config_path), auto_load=True)

        message = str(exc_info.value)
        assert "Variable 'API_TOKEN'" in message
        assert "typo" in message
        assert "default" in message
        assert "production" in message

    def test_variable_override_validation_rejects_invalid_origin(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(
            tmp_path,
            """
            variables:
              API_TOKEN:
                source: API_TOKEN
                origin: vault
            """,
        )

        with pytest.raises(ValueError) as exc_info:
            ConfigManager(str(config_path), auto_load=True)

        assert "Variable 'API_TOKEN'" in str(exc_info.value)
        assert "origin" in str(exc_info.value)
        assert "vault" in str(exc_info.value)


class TestNoDefaultEnvironment:
    """When ENVIRONMENT is unset and no default is defined."""

    YAML_NO_DEFAULT = """\
    environments:
      staging:
        origin: local
        dotenv_path: .env.staging
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
    """

    def test_no_default_no_env_var_returns_none(self, tmp_path, monkeypatch):
        """No immediate crash -- active_environment is None (deferred error)."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(tmp_path, self.YAML_NO_DEFAULT)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is None


# ===========================================================================
# Old YAML format (no environments key) -- backwards compatibility
# ===========================================================================


class TestBackwardsCompatibility:
    """Old YAML format without environments section works identically."""

    YAML_OLD_FORMAT = """\
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
    validation:
      required:
        - DB_PASSWORD
    """

    YAML_OLD_FORMAT_WITH_DEFAULT = """\
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
        default: yaml-default
    """

    def test_old_format_active_environment_is_none(self, tmp_path, monkeypatch):
        """Old format: active_environment is None."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT)
        write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is None

    def test_old_format_uses_param_secret_origin(self, tmp_path, monkeypatch):
        """Old format: secret_origin param works as before."""
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT)
        env_path = write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path), auto_load=False,
        )

        assert mgr.secret_origin == "local"

    def test_old_format_loads_successfully(self, tmp_path, monkeypatch):
        """Old format: full load cycle works."""
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT)
        env_path = write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path),
        )

        assert mgr.get("DB_PASSWORD") == "secret123"

    def test_old_format_resolution_precedence_os_environ_wins(
        self, tmp_path, monkeypatch
    ):
        """Old format: os.environ beats both .env file and YAML default."""
        monkeypatch.setenv("DB_PASSWORD", "from-os")
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT_WITH_DEFAULT)
        env_path = write_env(tmp_path, "DB_PASSWORD=from-dotenv\n")

        manager = ConfigManager(
            str(config_path), secret_origin="local", dotenv_path=str(env_path)
        )

        assert manager.get("DB_PASSWORD") == "from-os"

    def test_old_format_resolution_precedence_dotenv_wins_over_default(
        self, tmp_path, monkeypatch
    ):
        """Old format: .env file beats YAML default when os.environ not set."""
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT_WITH_DEFAULT)
        env_path = write_env(tmp_path, "DB_PASSWORD=from-dotenv\n")

        manager = ConfigManager(
            str(config_path), secret_origin="local", dotenv_path=str(env_path)
        )

        assert manager.get("DB_PASSWORD") == "from-dotenv"

    def test_old_format_resolution_precedence_default_fallback(
        self, tmp_path, monkeypatch
    ):
        """Old format: YAML default is used when os.environ and .env are empty."""
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        config_path = write_config(tmp_path, self.YAML_OLD_FORMAT_WITH_DEFAULT)
        env_path = write_env(tmp_path, "")

        manager = ConfigManager(
            str(config_path), secret_origin="local", dotenv_path=str(env_path)
        )

        assert manager.get("DB_PASSWORD") == "yaml-default"

    def test_old_format_variable_origin_override_works(
        self, tmp_path, monkeypatch
    ):
        """Old format: per-variable origin override resolves via correct loader."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        config_path = write_config(
            tmp_path,
            """
            variables:
              API_TOKEN:
                source: projects/app/secrets/TOKEN
                origin: gcp
            """,
        )

        class FakeLoader:
            def get_many(self, keys):
                return {key: "gcp-value" for key in keys}

        loader_calls: list[tuple[str, str | None, str | None]] = []

        def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None, **kwargs):
            loader_calls.append((origin, gcp_project_id, dotenv_path))
            return FakeLoader()

        monkeypatch.setattr(manager_module, "create_loader", fake_create_loader)

        manager = ConfigManager(str(config_path), auto_load=True)

        assert manager.get("API_TOKEN") == "gcp-value"
        assert len(loader_calls) == 1
        assert loader_calls[0][0] == "gcp"
        assert loader_calls[0][1] == "test-project"

    def test_old_format_variable_environment_override_raises(
        self, tmp_path, monkeypatch
    ):
        """Old format: per-variable environment override raises ValueError (no environments dict)."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(
            tmp_path,
            """
            variables:
              DB_PASSWORD:
                source: DB_PASSWORD
                environment: production
            """,
        )

        with pytest.raises(ValueError) as exc_info:
            ConfigManager(str(config_path), auto_load=True)

        message = str(exc_info.value)
        assert "DB_PASSWORD" in message
        assert "production" in message

    def test_old_format_via_init_config_and_require_config(
        self, tmp_path, monkeypatch
    ):
        """Old format: init_config / get_config / require_config work end-to-end."""
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = write_config(
            tmp_path,
            """
            variables:
              DB_PASSWORD:
                source: DB_PASSWORD
            validation:
              required:
                - DB_PASSWORD
            """,
        )
        env_path = write_env(tmp_path, "DB_PASSWORD=via-singleton\n")

        init_config(str(config_path), secret_origin="local", dotenv_path=str(env_path))

        assert get_config("DB_PASSWORD") == "via-singleton"
        assert require_config("DB_PASSWORD") == "via-singleton"

    def test_old_format_with_environment_var_set_does_not_raise(
        self, tmp_path, monkeypatch
    ):
        """Old format: ENVIRONMENT env var is ignored when no environments dict exists."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        config_path = write_config(
            tmp_path,
            """
            variables:
              DB_PASSWORD:
                source: DB_PASSWORD
                default: some-default
            """,
        )

        manager = ConfigManager(str(config_path), auto_load=False)

        assert manager.active_environment is None


# ===========================================================================
# Param overrides beat environment config values
# ===========================================================================


class TestParamOverrides:
    """When both environments YAML and explicit params exist, params win."""

    YAML_WITH_ENVS = """\
    environments:
      default:
        origin: gcp
        gcp_project_id: env-project
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
    """

    def test_secret_origin_param_overrides_env_config(self, tmp_path, monkeypatch):
        """secret_origin param wins over active environment's origin."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path), auto_load=False,
        )

        assert mgr.secret_origin == "local"

    def test_gcp_project_id_param_overrides_env_config(self, tmp_path, monkeypatch):
        """gcp_project_id param wins over active environment's gcp_project_id."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)

        mgr = ConfigManager(
            str(config_path), gcp_project_id="override-project",
            auto_load=False,
        )

        assert mgr.gcp_project_id == "override-project"

    def test_dotenv_path_param_overrides_env_config(self, tmp_path, monkeypatch):
        """dotenv_path param wins over active environment's dotenv_path."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        yaml_local = """\
        environments:
          default:
            origin: local
            dotenv_path: .env.from-env-config
        variables:
          DB_PASSWORD:
            source: DB_PASSWORD
        """
        config_path = write_config(tmp_path, yaml_local)
        custom_env = tmp_path / ".env.custom"
        custom_env.write_text("DB_PASSWORD=custom\n", encoding="utf-8")

        mgr = ConfigManager(
            str(config_path), dotenv_path=str(custom_env), auto_load=False,
        )

        # The param-provided path should be used, not the env config one
        assert mgr._dotenv_path == str(custom_env)


# ===========================================================================
# Singleton API with environments
# ===========================================================================


class TestSingletonWithEnvironments:
    """init_config / get_config / require_config work with environment configs."""

    YAML_WITH_ENVS = """\
    environments:
      default:
        origin: local
        dotenv_path: .env
    variables:
      DB_PASSWORD:
        source: DB_PASSWORD
    validation:
      required:
        - DB_PASSWORD
    """

    def test_init_config_with_environments(self, tmp_path, monkeypatch):
        """init_config works with new-format YAML."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = write_env(tmp_path)

        mgr = init_config(str(config_path), dotenv_path=str(env_path))

        assert get_config("DB_PASSWORD") == "secret123"
        assert require_config("DB_PASSWORD") == "secret123"

    def test_init_config_signatures_unchanged(self, tmp_path, monkeypatch):
        """init_config accepts all original kwargs."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = write_env(tmp_path)

        # All original kwargs should be accepted without error
        mgr = init_config(
            str(config_path),
            secret_origin="local",
            gcp_project_id=None,
            strict=False,
            auto_load=True,
            dotenv_path=str(env_path),
            debug=False,
        )

        assert isinstance(mgr, ConfigManager)


# ===========================================================================
# Phase 02: Encrypted dotenv per-environment configuration
# ===========================================================================


class TestEncryptedDotenvConfig:
    """Per-environment encrypted_dotenv configuration parsing."""

    YAML_ENCRYPTED = """\
    environments:
      staging:
        origin: local
        dotenv_path: .env.staging
        default: true
        encrypted_dotenv:
          enabled: true
          private_key:
            source: MY_CUSTOM_KEY
            secret_origin: local
            dotenv_path: .env.staging.keys
      production:
        origin: local
        dotenv_path: .env.production
    variables:
      API_KEY:
        source: API_KEY
    """

    def test_encrypted_env_has_config(self, tmp_path, monkeypatch):
        """Staging env has encrypted_dotenv.enabled = True."""
        from env_manager.environment import parse_environments
        from env_manager.utils import load_yaml
        config_path = write_config(tmp_path, self.YAML_ENCRYPTED)
        raw = load_yaml(str(config_path))
        envs = parse_environments(raw)
        staging = envs["staging"]
        assert staging.encrypted_dotenv is not None
        assert staging.encrypted_dotenv.enabled is True
        assert staging.encrypted_dotenv.private_key is not None
        assert staging.encrypted_dotenv.private_key.source == "MY_CUSTOM_KEY"
        assert staging.encrypted_dotenv.private_key.secret_origin == "local"
        assert staging.encrypted_dotenv.private_key.dotenv_path == ".env.staging.keys"

    def test_plaintext_env_has_no_config(self, tmp_path, monkeypatch):
        """Production env has encrypted_dotenv = None."""
        from env_manager.environment import parse_environments
        from env_manager.utils import load_yaml
        config_path = write_config(tmp_path, self.YAML_ENCRYPTED)
        raw = load_yaml(str(config_path))
        envs = parse_environments(raw)
        production = envs["production"]
        assert production.encrypted_dotenv is None

    def test_encrypted_disabled_treated_as_none(self, tmp_path):
        """encrypted_dotenv with enabled: false treated as None."""
        from env_manager.environment import parse_environments
        from env_manager.utils import load_yaml
        yaml_text = """\
        environments:
          dev:
            origin: local
            dotenv_path: .env.dev
            default: true
            encrypted_dotenv:
              enabled: false
        variables:
          X:
            source: X
        """
        config_path = write_config(tmp_path, yaml_text)
        raw = load_yaml(str(config_path))
        envs = parse_environments(raw)
        assert envs["dev"].encrypted_dotenv is None

    def test_invalid_secret_origin_defaults_to_local(self, tmp_path):
        """Unknown secret_origin defaults to 'local'."""
        from env_manager.environment import parse_environments
        from env_manager.utils import load_yaml
        yaml_text = """\
        environments:
          dev:
            origin: local
            dotenv_path: .env
            default: true
            encrypted_dotenv:
              enabled: true
              private_key:
                source: KEY
                secret_origin: aws
        variables:
          X:
            source: X
        """
        config_path = write_config(tmp_path, yaml_text)
        raw = load_yaml(str(config_path))
        envs = parse_environments(raw)
        assert envs["dev"].encrypted_dotenv.private_key.secret_origin == "local"
