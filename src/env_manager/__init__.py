"""env-manager package initialization."""

from .manager import ConfigManager, get_config, init_config, require_config
from .base import SecretLoader
from .environment import EnvironmentConfig
from .exceptions import (
    ConfigValidationError,
    ConfigValidationIssue,
    DecryptionError,
    DecryptionIssue,
)
from .factory import create_loader

__all__ = [
    "ConfigManager",
    "ConfigValidationError",
    "ConfigValidationIssue",
    "DecryptionError",
    "DecryptionIssue",
    "EnvironmentConfig",
    "get_config",
    "init_config",
    "require_config",
    "SecretLoader",
    "create_loader",
]

__version__ = "0.1.0"
