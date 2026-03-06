"""Integration tests for environment selection and backwards compatibility."""

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager, get_config, init_config, require_config


@pytest.fixture(autouse=True)
def reset_singleton():
    manager_module._SINGLETON = None
    yield
    manager_module._SINGLETON = None


# ---------------------------------------------------------------------------
# Helper to write a YAML config with a simple variable
# ---------------------------------------------------------------------------

def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dedent(yaml_text), encoding="utf-8")
    return config_path


def _write_env(tmp_path: Path, content: str = "DB_PASSWORD=secret123\n") -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


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
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
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
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
        _write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is not None
        assert mgr.active_environment.name == "default"

    def test_undefined_environment_raises_value_error(self, tmp_path, monkeypatch):
        """ENVIRONMENT=unknown raises ValueError with descriptive message."""
        monkeypatch.setenv("ENVIRONMENT", "unknown")
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)

        with pytest.raises(ValueError, match="unknown"):
            ConfigManager(str(config_path), auto_load=False)

    def test_undefined_environment_error_lists_available(self, tmp_path, monkeypatch):
        """Error message lists available environment names."""
        monkeypatch.setenv("ENVIRONMENT", "typo")
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)

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
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
        _write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.secret_origin == "local"

    def test_environment_gcp_project_id_used(self, tmp_path, monkeypatch):
        """Active environment's gcp_project_id is propagated."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        # Change cwd so find_dotenv doesn't discover the project's real .env
        monkeypatch.chdir(tmp_path)
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.gcp_project_id == "my-prod-project"


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
        config_path = _write_config(tmp_path, self.YAML_NO_DEFAULT)

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

    def test_old_format_active_environment_is_none(self, tmp_path, monkeypatch):
        """Old format: active_environment is None."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = _write_config(tmp_path, self.YAML_OLD_FORMAT)
        _write_env(tmp_path)

        mgr = ConfigManager(str(config_path), auto_load=False)

        assert mgr.active_environment is None

    def test_old_format_uses_param_secret_origin(self, tmp_path, monkeypatch):
        """Old format: secret_origin param works as before."""
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = _write_config(tmp_path, self.YAML_OLD_FORMAT)
        env_path = _write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path), auto_load=False,
        )

        assert mgr.secret_origin == "local"

    def test_old_format_loads_successfully(self, tmp_path, monkeypatch):
        """Old format: full load cycle works."""
        monkeypatch.delenv("SECRET_ORIGIN", raising=False)
        config_path = _write_config(tmp_path, self.YAML_OLD_FORMAT)
        env_path = _write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path),
        )

        assert mgr.get("DB_PASSWORD") == "secret123"


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
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = _write_env(tmp_path)

        mgr = ConfigManager(
            str(config_path), secret_origin="local",
            dotenv_path=str(env_path), auto_load=False,
        )

        assert mgr.secret_origin == "local"

    def test_gcp_project_id_param_overrides_env_config(self, tmp_path, monkeypatch):
        """gcp_project_id param wins over active environment's gcp_project_id."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)

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
        config_path = _write_config(tmp_path, yaml_local)
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
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = _write_env(tmp_path)

        mgr = init_config(str(config_path), dotenv_path=str(env_path))

        assert get_config("DB_PASSWORD") == "secret123"
        assert require_config("DB_PASSWORD") == "secret123"

    def test_init_config_signatures_unchanged(self, tmp_path, monkeypatch):
        """init_config accepts all original kwargs."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        config_path = _write_config(tmp_path, self.YAML_WITH_ENVS)
        env_path = _write_env(tmp_path)

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
