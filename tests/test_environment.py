from __future__ import annotations

import pytest

from env_manager.environment import EnvironmentConfig, parse_environments


def test_no_environments_key_returns_empty_dict():
    raw_config = {"variables": {"DB_HOST": {"type": "string"}}}
    result = parse_environments(raw_config)
    assert result == {}


def test_valid_local_environment():
    raw_config = {
        "environments": {
            "default": {
                "origin": "local",
                "dotenv_path": ".env.local",
            }
        }
    }
    result = parse_environments(raw_config)
    assert "default" in result
    cfg = result["default"]
    assert isinstance(cfg, EnvironmentConfig)
    assert cfg.name == "default"
    assert cfg.origin == "local"
    assert cfg.dotenv_path == ".env.local"
    assert cfg.gcp_project_id is None


def test_valid_gcp_environment():
    raw_config = {
        "environments": {
            "production": {
                "origin": "gcp",
                "gcp_project_id": "my-project",
            }
        }
    }
    result = parse_environments(raw_config)
    cfg = result["production"]
    assert cfg.name == "production"
    assert cfg.origin == "gcp"
    assert cfg.gcp_project_id == "my-project"
    assert cfg.dotenv_path is None


def test_origin_missing_raises_value_error():
    raw_config = {
        "environments": {
            "staging": {
                "dotenv_path": ".env.staging",
            }
        }
    }
    with pytest.raises(ValueError, match="staging"):
        parse_environments(raw_config)


def test_invalid_origin_raises_value_error():
    raw_config = {
        "environments": {
            "dev": {
                "origin": "aws",
            }
        }
    }
    with pytest.raises(ValueError, match="dev"):
        parse_environments(raw_config)


def test_local_origin_defaults_dotenv_path():
    raw_config = {
        "environments": {
            "default": {
                "origin": "local",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["default"].dotenv_path == ".env"


def test_local_origin_explicit_dotenv_path():
    raw_config = {
        "environments": {
            "staging": {
                "origin": "local",
                "dotenv_path": ".env.staging",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["staging"].dotenv_path == ".env.staging"


def test_gcp_without_project_id_raises_value_error():
    raw_config = {
        "environments": {
            "production": {
                "origin": "gcp",
            }
        }
    }
    with pytest.raises(ValueError, match="production"):
        parse_environments(raw_config)


def test_gcp_ignores_dotenv_path():
    raw_config = {
        "environments": {
            "production": {
                "origin": "gcp",
                "gcp_project_id": "proj-1",
                "dotenv_path": ".env.prod",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["production"].dotenv_path is None


def test_local_ignores_gcp_project_id():
    raw_config = {
        "environments": {
            "dev": {
                "origin": "local",
                "gcp_project_id": "should-be-ignored",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["dev"].gcp_project_id is None
    assert result["dev"].dotenv_path == ".env"


def test_dotenv_path_filename_kept_as_is():
    raw_config = {
        "environments": {
            "staging": {
                "origin": "local",
                "dotenv_path": ".env.staging",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["staging"].dotenv_path == ".env.staging"


def test_dotenv_path_full_path_kept_as_is():
    raw_config = {
        "environments": {
            "staging": {
                "origin": "local",
                "dotenv_path": "/app/.env",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["staging"].dotenv_path == "/app/.env"


def test_environments_not_a_dict_raises_value_error():
    raw_config = {"environments": ["default", "staging"]}
    with pytest.raises(ValueError, match="environments"):
        parse_environments(raw_config)


def test_individual_environment_not_a_dict_raises_value_error():
    raw_config = {
        "environments": {
            "broken": "not-a-dict",
        }
    }
    with pytest.raises(ValueError, match="broken"):
        parse_environments(raw_config)


def test_multiple_environments_parse_independently():
    raw_config = {
        "environments": {
            "default": {
                "origin": "local",
            },
            "staging": {
                "origin": "local",
                "dotenv_path": ".env.staging",
            },
            "production": {
                "origin": "gcp",
                "gcp_project_id": "prod-project",
            },
        }
    }
    result = parse_environments(raw_config)
    assert len(result) == 3
    assert result["default"].origin == "local"
    assert result["default"].dotenv_path == ".env"
    assert result["staging"].dotenv_path == ".env.staging"
    assert result["production"].origin == "gcp"
    assert result["production"].gcp_project_id == "prod-project"
    assert result["production"].dotenv_path is None


def test_origin_normalized_to_lowercase():
    raw_config = {
        "environments": {
            "dev": {
                "origin": "LOCAL",
            }
        }
    }
    result = parse_environments(raw_config)
    assert result["dev"].origin == "local"


def test_dataclass_fields():
    cfg = EnvironmentConfig(name="test", origin="local", dotenv_path=".env")
    assert cfg.name == "test"
    assert cfg.origin == "local"
    assert cfg.dotenv_path == ".env"
    assert cfg.gcp_project_id is None
