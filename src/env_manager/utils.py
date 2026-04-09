"""Utility helpers for env-manager."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.logging import RichHandler

__all__ = [
    "PrettyLogger",
    "logger",
    "mask_secret",
    "coerce_type",
    "load_yaml",
]

PrettyLogger = logging.getLoggerClass()
logger = logging.getLogger("env-manager")


def _configure_logging() -> None:
    """Configure logging with rich handler if not already configured."""
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(
            RichHandler(
                console=Console(stderr=True),
                rich_tracebacks=True,
                show_time=False,
                show_path=False,
            )
        )
        root.setLevel(logging.INFO)


_configure_logging()


SUPPORTED_TYPES = {"str", "int", "float", "bool"}


def mask_secret(value: str) -> str:
    """Mask a secret for safe logging."""

    if len(value) < 10:
        return "*" * 10
    return f"{value[:2]}****{value[-4:]}"


def coerce_type(raw_value: Any, target_type: str, variable_name: str) -> Any:
    """Convert ``raw_value`` to ``target_type`` with informative errors."""

    if target_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported type '{target_type}' for variable '{variable_name}'"
        )

    if raw_value is None:
        return None

    if target_type == "str":
        # Convert booleans to lowercase string for consistency
        if isinstance(raw_value, bool):
            return "true" if raw_value else "false"
        return str(raw_value)

    value_str = str(raw_value)

    if target_type == "int":
        try:
            return int(value_str)
        except ValueError as exc:
            raise ValueError(
                f"Cannot convert '{variable_name}' value '{value_str}' to int"
            ) from exc

    if target_type == "float":
        try:
            return float(value_str)
        except ValueError as exc:
            raise ValueError(
                f"Cannot convert '{variable_name}' value '{value_str}' to float"
            ) from exc

    if value_str in {"true", "True", "1"}:
        return True
    if value_str in {"false", "False", "0"}:
        return False

    raise ValueError(
        "Invalid boolean value for "
        f"'{variable_name}': '{value_str}'. Must be one of: 'true', 'True', "
        "'1', 'false', 'False', '0'"
    )


def load_yaml(path: str) -> dict[str, Any]:
    """Load a YAML configuration file safely."""

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file '{config_path}' does not exist.")

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Configuration file '{config_path}' must define a mapping at the root."
        )

    return data
