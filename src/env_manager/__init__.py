"""env-manager package initialization."""

from .manager import (
    ConfigManager,
    _reset_singleton,
    get_config,
    init_config,
    require_config,
)
from .base import SecretLoader
from .environment import EnvironmentConfig, parse_environments
from .exceptions import (
    ConfigValidationError,
    ConfigValidationIssue,
    DecryptionError,
    DecryptionIssue,
)
from .factory import create_loader
from .loaders import DotEnvLoader, GCPSecretLoader
from .utils import coerce_type, load_yaml, mask_secret

__all__ = [
    "_reset_singleton",
    "coerce_type",
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
    "DotEnvLoader",
    "GCPSecretLoader",
    "load_yaml",
    "mask_secret",
    "parse_environments",
]

__version__ = "0.4.1"
