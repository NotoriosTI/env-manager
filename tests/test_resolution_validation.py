from __future__ import annotations

from pathlib import Path

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager
from conftest import write_config, write_env, write_repo_config


def test_required_sourced_variable_missing_raises_runtime_error_with_context(
    tmp_path, capsys
):
    config_path = write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env.runtime
        variables:
          API_KEY:
            source: API_KEY
        validation:
          required:
            - API_KEY
        """,
    )
    (tmp_path / ".env.runtime").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc.value)
    assert "Required variable 'API_KEY' not found" in message
    assert "environment 'default'" in message
    assert str((tmp_path / ".env.runtime").resolve()) in message
    assert "API_KEY" in capsys.readouterr().out


def test_required_sourced_variable_uses_yaml_default_and_warns(tmp_path, capsys):
    config_path = write_config(
        tmp_path,
        """
        variables:
          API_KEY:
            source: API_KEY
            default: "fallback-key"
        validation:
          required:
            - API_KEY
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("API_KEY") == "fallback-key"
    output = capsys.readouterr().out
    assert "Required variable 'API_KEY' missing from source; using YAML default" in output
    assert "environment 'default'" in output


def test_optional_sourced_variable_without_default_resolves_none_and_warns(
    tmp_path, capsys
):
    config_path = write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
        validation:
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("OPTIONAL_TOKEN") is None
    output = capsys.readouterr().out
    assert "Optional variable 'OPTIONAL_TOKEN' resolved to None" in output
    assert "environment 'default'" in output


def test_optional_sourced_variable_with_yaml_default_is_quiet(tmp_path, capsys):
    config_path = write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
            default: "quiet-default"
        validation:
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_file),
        auto_load=True,
    )

    assert manager.get("OPTIONAL_TOKEN") == "quiet-default"
    output = capsys.readouterr().out
    assert "Optional variable 'OPTIONAL_TOKEN'" not in output


def test_strict_mode_raises_before_optional_fallback(tmp_path):
    config_path = write_config(
        tmp_path,
        """
        variables:
          OPTIONAL_TOKEN:
            source: OPTIONAL_TOKEN
        validation:
          strict: true
          optional:
            - OPTIONAL_TOKEN
        """,
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(
            str(config_path),
            secret_origin="local",
            dotenv_path=str(env_file),
            auto_load=True,
        )

    assert "Strict mode" in str(exc.value)
    assert "OPTIONAL_TOKEN" in str(exc.value)


def test_gcp_runtime_context_is_included_in_missing_value_messages(
    tmp_path, monkeypatch, capsys
):
    config_path = write_config(
        tmp_path,
        """
        environments:
          default:
            origin: gcp
            gcp_project_id: app-prod
        variables:
          API_TOKEN:
            source: projects/app-prod/secrets/API_TOKEN
        validation:
          optional:
            - API_TOKEN
        """,
    )

    class FakeLoader:
        def get_many(self, keys):
            return {key: None for key in keys}

    monkeypatch.setattr(
        manager_module,
        "create_loader",
        lambda *args, **kwargs: FakeLoader(),
    )

    manager = ConfigManager(
        str(config_path),
        gcp_project_id="app-prod",
        auto_load=True,
    )

    assert manager.get("API_TOKEN") is None
    output = capsys.readouterr().out
    assert "environment 'default'" in output
    assert "GCP project 'app-prod'" in output


def test_missing_explicit_per_variable_dotenv_raises_only_when_lookup_needs_file(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("API_KEY", raising=False)

    config_path = write_repo_config(
        repo_root,
        """
        environments:
          staging:
            origin: local
            dotenv_path: env/.env.staging
        variables:
          API_KEY:
            source: API_KEY
            dotenv_path: secrets/.env.missing
        validation:
          required:
            - API_KEY
        """,
    )
    (repo_root / "env").mkdir()
    (repo_root / "env" / ".env.staging").write_text("API_KEY=from-staging\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc.value)
    assert "API_KEY" in message
    assert "environment 'staging'" in message
    assert str((repo_root / "secrets" / ".env.missing").resolve()) in message


def test_missing_explicit_per_variable_dotenv_is_bypassed_by_os_environ(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("API_KEY", "from-os")

    config_path = write_repo_config(
        repo_root,
        """
        environments:
          staging:
            origin: local
            dotenv_path: env/.env.staging
        variables:
          API_KEY:
            source: API_KEY
            dotenv_path: secrets/.env.missing
        validation:
          required:
            - API_KEY
        """,
    )
    (repo_root / "env").mkdir()
    (repo_root / "env" / ".env.staging").write_text("API_KEY=from-staging\n", encoding="utf-8")

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("API_KEY") == "from-os"


# ===========================================================================
# Schema error path tests for invalid variable definitions
# ===========================================================================


def test_empty_dotenv_path_override_raises_value_error(tmp_path, monkeypatch):
    """dotenv_path: '' (empty string) raises ValueError with variable name and 'dotenv_path'."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config_path = write_config(
        tmp_path,
        """
        variables:
          DB_PASSWORD:
            source: DB_PASSWORD
            dotenv_path: ""
        """,
    )

    with pytest.raises(ValueError, match="DB_PASSWORD") as exc_info:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc_info.value)
    assert "dotenv_path" in message


def test_non_string_source_raises_value_error(tmp_path, monkeypatch):
    """source: 123 (non-string integer) raises ValueError with variable name and 'source'."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config_path = write_config(
        tmp_path,
        """
        variables:
          DB_PASSWORD:
            source: 123
        """,
    )

    with pytest.raises(ValueError, match="DB_PASSWORD") as exc_info:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc_info.value)
    assert "source" in message


def test_empty_environment_override_raises_value_error(tmp_path, monkeypatch):
    """environment: '' (empty string) raises ValueError with variable name and 'environment'."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config_path = write_config(
        tmp_path,
        """
        variables:
          DB_PASSWORD:
            source: DB_PASSWORD
            environment: ""
        """,
    )

    with pytest.raises(ValueError, match="DB_PASSWORD") as exc_info:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc_info.value)
    assert "environment" in message


def test_variables_section_as_list_raises_value_error(tmp_path, monkeypatch):
    """variables: [...] (list instead of dict) raises ValueError with 'variables' and 'mapping'."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config_path = write_config(
        tmp_path,
        """
        variables:
          - DB_PASSWORD
        """,
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc_info.value)
    assert "variables" in message
    assert "mapping" in message


def test_validation_section_as_string_raises_value_error(tmp_path, monkeypatch):
    """validation: 'strict' (string instead of dict) raises ValueError with 'validation' and 'mapping'."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config_path = write_config(
        tmp_path,
        """
        variables:
          DB_PASSWORD:
            source: DB_PASSWORD
        validation: strict
        """,
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc_info.value)
    assert "validation" in message
    assert "mapping" in message


def test_gcp_origin_with_dotenv_path_ignores_dotenv(tmp_path, monkeypatch):
    """origin: gcp + dotenv_path override: gcp loader gets dotenv_path from the override (re-applied after gcp clears it)."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    config_path = write_config(
        tmp_path,
        """
        environments:
          default:
            origin: local
            dotenv_path: .env
        variables:
          GCP_SECRET:
            source: projects/app/secrets/GCP_SECRET
            origin: gcp
            dotenv_path: secrets/.env.special
        """,
    )
    write_env(tmp_path)

    loader_calls: list[tuple[str, str | None, str | None]] = []

    class FakeLoader:
        def get_many(self, keys):
            return {key: "gcp-value" for key in keys}

    def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None, **kwargs):
        loader_calls.append((origin, gcp_project_id, dotenv_path))
        return FakeLoader()

    monkeypatch.setattr(manager_module, "create_loader", fake_create_loader)

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("GCP_SECRET") == "gcp-value"
    assert len(loader_calls) >= 1
    gcp_call = next(c for c in loader_calls if c[0] == "gcp")
    assert gcp_call[0] == "gcp"
    assert gcp_call[1] == "test-project"
    # dotenv_path override is re-applied after gcp clears it -- verify it's the resolved path
    expected_dotenv = str((tmp_path / "secrets" / ".env.special").resolve())
    assert gcp_call[2] == expected_dotenv
