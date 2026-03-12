"""Test SECRET_ORIGIN detection from .env file."""

from __future__ import annotations

from env_manager import ConfigManager
from conftest import write_config


def test_secret_origin_from_dotenv(tmp_path):
    """SECRET_ORIGIN is detected from .env when no constructor param or os.environ override is present."""
    config = write_config(
        tmp_path,
        """
        variables:
          TEST_VAR:
            source: TEST_VAR
            type: str
            default: "test_value"
        validation:
          strict: false
        """,
    )

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("SECRET_ORIGIN=gcp\nGCP_PROJECT_ID=test-project\n", encoding="utf-8")

    manager = ConfigManager(
        str(config),
        dotenv_path=str(dotenv_file),
        auto_load=False,
    )

    assert manager.secret_origin == "gcp"
    assert manager.gcp_project_id == "test-project"
