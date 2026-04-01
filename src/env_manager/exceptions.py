"""Custom exception types for env-manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ConfigValidationIssue:
    """One validation problem discovered during load()."""
    variable: str
    message: str
    context: Optional[object] = None


class ConfigValidationError(Exception):
    """Aggregated validation failures from a single load() attempt."""

    def __init__(self, issues: list[ConfigValidationIssue]) -> None:
        self.issues = issues
        count = len(issues)
        var_list = ", ".join(f"'{i.variable}'" for i in issues)
        super().__init__(
            f"Configuration validation failed for {count} variable{'s' if count != 1 else ''}: {var_list}."
        )


@dataclass(frozen=True)
class DecryptionIssue:
    """One decryption failure for a single dotenv variable."""
    key: str
    message: str


class DecryptionError(Exception):
    """Aggregated decryption failures from a single load attempt."""

    def __init__(self, issues: list[DecryptionIssue]) -> None:
        self.issues = issues
        count = len(issues)
        key_list = ", ".join(f"'{i.key}'" for i in issues)
        super().__init__(
            f"Decryption failed for {count} key{'s' if count != 1 else ''}: {key_list}."
        )
