from __future__ import annotations

import os
from pathlib import Path

import pytest

import env_manager.manager as manager_module
from env_manager import ConfigManager, get_config, init_config, require_config
from conftest import write_repo_config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def prod_config(tmp_path: Path) -> Path:
    config_source = FIXTURES / "prod_config.example.yaml"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_source.read_text(), encoding="utf-8")
    return config_path


@pytest.mark.integration
def test_production_like_flow(prod_config: Path):
    manager_module._SINGLETON = None  # ensure clean singleton state

    if not os.getenv("RUN_REAL_GCP_TESTS"):
        pytest.skip("Set RUN_REAL_GCP_TESTS=1 to run GCP integration test.")

    gcp_manager = ConfigManager(
        str(prod_config),
        secret_origin="gcp",
        gcp_project_id="notorios",
    )

    required_keys = {
        "ODOO_PROD_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SLACK_BOT_TOKEN",
    }

    for key in required_keys:
        value = gcp_manager.require(key)
        assert isinstance(value, str) and value
        assert os.environ[key] == value

    manager_module._SINGLETON = None
    init_config(
        str(prod_config),
        secret_origin="gcp",
        gcp_project_id="notorios",
    )
    for key in required_keys:
        value = require_config(key)
        assert isinstance(value, str) and value

    for key in required_keys:
        os.environ.pop(key, None)

    manager_module._SINGLETON = None
    env_file = prod_config.parent / ".env"
    env_values = {
        "ODOO_PROD_URL": "https://odoo.local",
        "OPENAI_API_KEY": "sk-test-openai",
        "ANTHROPIC_API_KEY": "anthropic-test-key",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
    }
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in env_values.items()),
        encoding="utf-8",
    )

    local_manager = ConfigManager(
        str(prod_config),
        secret_origin="local",
        dotenv_path=str(env_file),
    )

    for key, expected in env_values.items():
        assert local_manager.require(key) == expected
        assert os.environ[key] == expected

    manager_module._SINGLETON = None
    init_config(
        str(prod_config),
        secret_origin="local",
        dotenv_path=str(env_file),
    )

    for key, expected in env_values.items():
        assert get_config(key) == expected

    manager_module._SINGLETON = None


def test_mixed_sources_load_in_one_eager_pass(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("DEFAULT_TOKEN", raising=False)
    monkeypatch.delenv("OVERRIDE_TOKEN", raising=False)
    monkeypatch.delenv("PINNED_SECRET", raising=False)
    monkeypatch.delenv("GCP_SECRET", raising=False)

    config_path = write_repo_config(
        repo_root,
        """
environments:
  staging:
    origin: local
    dotenv_path: env/.env.staging
  production:
    origin: local
    dotenv_path: env/.env.production
  cloud:
    origin: gcp
    gcp_project_id: prod-123
variables:
  DEFAULT_TOKEN:
    source: DEFAULT_TOKEN
  OVERRIDE_TOKEN:
    source: OVERRIDE_TOKEN
    dotenv_path: secrets/.env.override
  PINNED_SECRET:
    source: PINNED_SECRET
    environment: production
  GCP_SECRET:
    source: projects/prod-123/secrets/GCP_SECRET
    environment: cloud
validation:
  strict: false
""",
    )
    (repo_root / "env").mkdir()
    (repo_root / "secrets").mkdir()
    (repo_root / "env" / ".env.staging").write_text(
        "DEFAULT_TOKEN=from-staging\n", encoding="utf-8"
    )
    (repo_root / "env" / ".env.production").write_text(
        "PINNED_SECRET=from-production\n", encoding="utf-8"
    )
    (repo_root / "secrets" / ".env.override").write_text(
        "OVERRIDE_TOKEN=from-override\n", encoding="utf-8"
    )

    class FakeLoader:
        def __init__(self, values):
            self._values = values

        def get_many(self, keys):
            return {key: self._values.get(key) for key in keys}

    calls: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []

    def fake_create_loader(origin, *, gcp_project_id=None, dotenv_path=None):
        calls.append((origin, gcp_project_id, dotenv_path, tuple()))
        if origin == "gcp":
            return FakeLoader({"projects/prod-123/secrets/GCP_SECRET": "from-gcp"})
        return manager_module.create_loader(origin, gcp_project_id=gcp_project_id, dotenv_path=dotenv_path)

    original_create_loader = manager_module.create_loader

    def recording_create_loader(origin, *, gcp_project_id=None, dotenv_path=None):
        if origin == "gcp":
            calls.append((origin, gcp_project_id, dotenv_path, ("projects/prod-123/secrets/GCP_SECRET",)))
            return FakeLoader({"projects/prod-123/secrets/GCP_SECRET": "from-gcp"})
        calls.append((origin, gcp_project_id, dotenv_path, tuple()))
        return original_create_loader(
            origin, gcp_project_id=gcp_project_id, dotenv_path=dotenv_path
        )

    monkeypatch.setattr(manager_module, "create_loader", recording_create_loader)

    manager = ConfigManager(str(config_path), auto_load=True)

    assert manager.get("DEFAULT_TOKEN") == "from-staging"
    assert manager.get("OVERRIDE_TOKEN") == "from-override"
    assert manager.get("PINNED_SECRET") == "from-production"
    assert manager.get("GCP_SECRET") == "from-gcp"
    assert ("gcp", "prod-123", None, ("projects/prod-123/secrets/GCP_SECRET",)) in calls
