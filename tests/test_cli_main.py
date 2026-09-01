"""Contrato del dispatcher `env-manager <acción>` (blueprint §1.7).

Espejo de tests/cli-main.test.ts en el repo JS: mismos casos, mismos exit codes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from env_manager.cli import exit_codes

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "env_manager.cli.main", *args],
        capture_output=True,
        text=True,
        input=stdin,
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )


class TestExitCodes:
    def test_help_is_success(self):
        result = run_cli("--help")
        assert result.returncode == exit_codes.OK
        assert "env-manager" in result.stdout

    def test_no_action_is_usage_error(self):
        result = run_cli()
        assert result.returncode == exit_codes.USAGE

    def test_unknown_action_is_usage_error(self):
        result = run_cli("bogus")
        assert result.returncode == exit_codes.USAGE

    def test_bad_format_is_usage_error(self):
        result = run_cli("encrypt", "x", "--format", "bogus")
        assert result.returncode == exit_codes.USAGE

    def test_missing_file_is_operation_error(self):
        result = run_cli("decrypt", "/tmp/env-manager-does-not-exist.env")
        assert result.returncode == exit_codes.OPERATION
        assert "File not found" in result.stderr

    @pytest.mark.parametrize(
        "args",
        [
            ("secrets",),
            ("secrets", "set", "app-config", "--key", "K"),
            ("secrets", "list", "app-config"),
        ],
    )
    def test_incomplete_secrets_invocations_are_usage_errors(self, args):
        assert run_cli(*args).returncode == exit_codes.USAGE


class TestStreams:
    def test_version_goes_to_stdout_alone(self):
        result = run_cli("--version")
        assert result.returncode == exit_codes.OK
        assert result.stdout.strip()
        assert result.stderr == ""

    def test_errors_go_to_stderr_not_stdout(self):
        result = run_cli("decrypt", "/tmp/env-manager-does-not-exist.env")
        assert result.stdout == ""
        assert "Error:" in result.stderr


class TestDeprecatedAliases:
    def test_encrypt_alias_warns_on_stderr(self):
        result = subprocess.run(
            [sys.executable, "-c", "from env_manager.cli.encrypt import main; main()", "--help"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
        )
        assert "deprecated" in result.stderr
        assert result.returncode == exit_codes.OK

    def test_decrypt_alias_warns_on_stderr(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from env_manager.cli.decrypt_shim import main; main()",
                "--help",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
        )
        assert "deprecated" in result.stderr
        assert result.returncode == exit_codes.OK
