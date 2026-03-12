"""Test configuration for env-manager."""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

import pytest

import env_manager.manager as manager_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests start with a clean slate for key env variables."""
    manager_module._SINGLETON = None
    for key in (
        "DB_PASSWORD",
        "PORT",
        "DEBUG_MODE",
        "TIMEOUT",
        "GCP_PROJECT_ID",
        "SECRET_ORIGIN",
        "API_KEY",
        "OPTIONAL",
        "WORKERS",
        "ENVIRONMENT",
        "DEFAULT_TOKEN",
        "OVERRIDE_TOKEN",
        "PINNED_SECRET",
        "GCP_SECRET",
        "SHARED_TOKEN",
        "OVERRIDDEN_TOKEN",
        "LOCAL_ONLY_TOKEN",
        "OPTIONAL_TOKEN",
        "API_TOKEN",
        "PROD_LOCAL_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    manager_module._SINGLETON = None


# ---------------------------------------------------------------------------
# Shared helper functions for writing test fixtures
# ---------------------------------------------------------------------------


def write_config(tmp_path: Path, yaml_text: str) -> Path:
    """Write dedented yaml_text to tmp_path/config.yaml and return the path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dedent(yaml_text), encoding="utf-8")
    return config_path


def write_env(tmp_path: Path, content: str = "DB_PASSWORD=secret123\n") -> Path:
    """Write content to tmp_path/.env and return the path."""
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def write_repo_config(repo_root: Path, yaml_text: str) -> Path:
    """Write a minimal pyproject.toml to repo_root, create repo_root/config/,
    write dedented yaml to config.yaml inside it, and return the config path.
    """
    (repo_root / "pyproject.toml").write_text(
        "[project]\nname='test-app'\n", encoding="utf-8"
    )
    config_dir = repo_root / "config"
    config_dir.mkdir()
    return write_config(config_dir, yaml_text)
