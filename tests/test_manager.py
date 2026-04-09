from __future__ import annotations

import os
from pathlib import Path

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager, get_config, init_config, require_config
from conftest import write_config

try:
    import ecies  # noqa: F401

    ECIES_AVAILABLE = True
except ImportError:
    ECIES_AVAILABLE = False

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _prepare_config(tmp_path: Path) -> tuple[Path, Path]:
    config_source = FIXTURES / "test_config.example.yaml"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_source.read_text(), encoding="utf-8")
    env_path = tmp_path / ".env"
    return config_path, env_path


def test_config_manager_local_loading(tmp_path):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text(
        "\n".join(
            [
                "DB_PASSWORD=password123",
                "PORT=9000",
                "DEBUG_MODE=true",
                "TIMEOUT=2.75",
                "GCP_PROJECT_ID=test-project",
            ]
        ),
        encoding="utf-8",
    )

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
    )

    assert manager.get("DB_PASSWORD") == "password123"
    assert manager.require("DB_PASSWORD") == "password123"
    assert manager.get("PORT") == 9000
    assert manager.get("DEBUG_MODE") is True
    assert manager.get("TIMEOUT") == 2.75
    assert os.environ["DB_PASSWORD"] == "password123"
    assert os.environ["GCP_PROJECT_ID"] == "test-project"


def test_missing_required_variable_raises(tmp_path):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text("PORT=9000\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(
            str(config_path),
            secret_origin="local",
            dotenv_path=str(env_path),
        )
    assert "Required variable 'DB_PASSWORD' not found" in str(exc.value)


def test_optional_variable_with_default_is_quiet(tmp_path, capsys):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text("DB_PASSWORD=password123\n", encoding="utf-8")

    manager = ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
    )

    output = capsys.readouterr().out
    assert "Optional variable DEBUG_MODE" not in output
    assert manager.get("DEBUG_MODE") is False


def test_strict_mode_raises_on_missing(tmp_path):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(
            str(config_path),
            secret_origin="local",
            dotenv_path=str(env_path),
            strict=True,
        )
    assert "Strict mode:" in str(exc.value)
    assert "DB_PASSWORD" in str(exc.value)


def test_singleton_api(tmp_path):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text("DB_PASSWORD=password123\n", encoding="utf-8")

    init_config(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
    )

    assert get_config("DB_PASSWORD") == "password123"
    assert require_config("DEBUG_MODE") is False


def test_reinit_logs_warning(tmp_path, capsys):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text("DB_PASSWORD=password123\n", encoding="utf-8")

    init_config(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
    )
    capsys.readouterr()
    init_config(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
    )

    output = capsys.readouterr().err
    assert "Configuration manager already initialised" in output


def test_debug_parameter_disables_masking(tmp_path, capsys):
    config_path, env_path = _prepare_config(tmp_path)
    env_path.write_text(
        "\n".join(
            [
                "DB_PASSWORD=password123",
                "PORT=1234",
                "DEBUG_MODE=true",
                "TIMEOUT=3.14",
            ]
        ),
        encoding="utf-8",
    )

    ConfigManager(
        str(config_path),
        secret_origin="local",
        dotenv_path=str(env_path),
        debug=True,
    )

    output = capsys.readouterr().err
    assert "Loaded DB_PASSWORD: password123" in output


def test_missing_active_environment_dotenv_is_deferred_until_lookup_needed(
    tmp_path, capsys
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
variables:
  DB_PASSWORD:
    source: DB_PASSWORD
environments:
  default:
    origin: local
    dotenv_path: .env.missing
validation:
  required:
    - DB_PASSWORD
        """.strip(),
        encoding="utf-8",
    )
    os.environ["DB_PASSWORD"] = "from-env"

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("DB_PASSWORD") == "from-env"
    output = capsys.readouterr().out
    assert str((tmp_path / ".env.missing").resolve()) not in output


def test_missing_active_environment_dotenv_raises_with_absolute_path_when_needed(
    tmp_path,
):
    config_path = tmp_path / "config.yaml"
    missing_path = (tmp_path / ".env.missing").resolve()
    config_path.write_text(
        """
variables:
  DB_PASSWORD:
    source: DB_PASSWORD
environments:
  default:
    origin: local
    dotenv_path: .env.missing
validation:
  required:
    - DB_PASSWORD
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as exc:
        ConfigManager(str(config_path), auto_load=True)

    message = str(exc.value)
    assert "environment 'default'" in message
    assert str(missing_path) in message


# ---------------------------------------------------------------------------
# ENC-06: NotImplementedError for GCP + encrypted combination
# ---------------------------------------------------------------------------


def test_gcp_encrypted_raises_not_implemented(tmp_path, monkeypatch):
    """GCP origin + encrypted_dotenv raises NotImplementedError."""
    yaml_text = """\
    environments:
      prod:
        origin: gcp
        gcp_project_id: my-project
        default: true
        encrypted_dotenv:
          enabled: true
    variables:
      SECRET:
        source: SECRET
    """
    config_path = write_config(tmp_path, yaml_text)
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(NotImplementedError, match="non-local origins"):
        ConfigManager(str(config_path), auto_load=True)


# ---------------------------------------------------------------------------
# ENC-01: old-format encrypted_dotenv top-level block
# ---------------------------------------------------------------------------


def test_old_format_encrypted_dotenv_top_level(tmp_path, monkeypatch):
    """Old-format config with top-level encrypted_dotenv.enabled works."""
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=plain_value\n")
    yaml_text = """\
    encrypted_dotenv:
      enabled: true
    variables:
      API_KEY:
        source: API_KEY
    """
    config_path = write_config(tmp_path, yaml_text)
    monkeypatch.chdir(tmp_path)
    # Should not error -- encrypted is enabled but the value is plaintext (no encrypted: prefix)
    cm = ConfigManager(str(config_path), auto_load=True)
    assert cm.get("API_KEY") == "plain_value"


# ---------------------------------------------------------------------------
# ENC-05: custom private key source name
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ECIES_AVAILABLE, reason="eciespy not installed")
def test_custom_private_key_source_used(tmp_path, monkeypatch):
    """Custom private_key.source name is resolved from environment."""
    import shutil

    fixtures = Path(__file__).resolve().parent / "fixtures"
    env_src = fixtures / ".env.encrypted"
    shutil.copy(env_src, tmp_path / ".env.staging")
    yaml_text = """\
    environments:
      staging:
        origin: local
        dotenv_path: .env.staging
        default: true
        encrypted_dotenv:
          enabled: true
          private_key:
            source: MY_DECRYPT_KEY
            secret_origin: local
    variables:
      HELLO:
        source: HELLO
    """
    config_path = write_config(tmp_path, yaml_text)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "MY_DECRYPT_KEY",
        "81dac4d2c42e67a2c6542d3b943a4674a05c4be5e7e5a40a689be7a3bd49a07e",
    )
    monkeypatch.chdir(tmp_path)
    cm = ConfigManager(str(config_path), auto_load=True)
    assert cm.get("HELLO") == "world"


# ---------------------------------------------------------------------------
# ENC-04: shared dotenv_path with different environment_name gets separate loaders
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ECIES_AVAILABLE, reason="eciespy not installed")
def test_shared_dotenv_path_different_env_name_separate_loaders(tmp_path, monkeypatch):
    """Two environments sharing a dotenv_path but different environment_name
    must produce separate loaders so the correct DOTENV_PRIVATE_KEY_<ENV>
    suffix is tried for each. Regression test for cache_key omitting
    environment_name."""
    import shutil

    fixtures = Path(__file__).resolve().parent / "fixtures"
    env_src = fixtures / ".env.encrypted"
    # Both environments point to the same dotenv file
    shutil.copy(env_src, tmp_path / ".env.shared")
    yaml_text = """\
    environments:
      alpha:
        origin: local
        dotenv_path: .env.shared
        encrypted_dotenv:
          enabled: true
      beta:
        origin: local
        dotenv_path: .env.shared
        default: true
        encrypted_dotenv:
          enabled: true
    variables:
      HELLO:
        source: HELLO
    """
    config_path = write_config(tmp_path, yaml_text)
    monkeypatch.setenv("APP_ENV", "beta")
    # Set env-specific key for beta only
    monkeypatch.setenv(
        "DOTENV_PRIVATE_KEY_BETA",
        "81dac4d2c42e67a2c6542d3b943a4674a05c4be5e7e5a40a689be7a3bd49a07e",
    )
    monkeypatch.delenv("DOTENV_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("DOTENV_PRIVATE_KEY_ALPHA", raising=False)
    monkeypatch.chdir(tmp_path)
    cm = ConfigManager(str(config_path), auto_load=True)
    # beta should decrypt successfully using DOTENV_PRIVATE_KEY_BETA
    assert cm.get("HELLO") == "world"
