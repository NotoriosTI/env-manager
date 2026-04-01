---
phase: 03-cli-encryption-script
plan: "02"
subsystem: cli
tags: [encryption, cli, argparse, console_scripts, pyproject, entry-point]
dependency_graph:
  requires:
    - 03-01 (encrypt_dotenv_file() function in src/env_manager/cli/encrypt.py)
  provides:
    - main() entry point with argparse CLI wrapping encrypt_dotenv_file
    - env-manager-encrypt console_script registered in pyproject.toml
  affects:
    - src/env_manager/cli/encrypt.py (main() appended)
    - pyproject.toml ([project.scripts] section added)
    - tests/test_cli_encrypt.py (TestCLIEntryPoint class added)
tech_stack:
  added: []
  patterns:
    - argparse entry point with lazy imports inside main()
    - console_scripts registration in pyproject.toml [project.scripts]
    - uv sync for console_script activation
key_files:
  created: []
  modified:
    - src/env_manager/cli/encrypt.py
    - pyproject.toml
    - tests/test_cli_encrypt.py
decisions:
  - "argparse inside main() keeps import overhead at call time only"
  - "[project.scripts] placed between [project.optional-dependencies] and [tool.poetry] to match pyproject.toml structure"
  - "Pre-existing 11 test failures (APP_ENV rename regression from Phase 02) documented as out-of-scope deferred items; no new failures introduced"
metrics:
  duration_seconds: 420
  completed_date: "2026-04-01"
  tasks_completed: 2
  files_created: 0
  files_modified: 3
requirements:
  - CLI-08
  - CLI-09
---

# Phase 03 Plan 02: CLI Entry Point Wiring Summary

**One-liner:** argparse main() added to encrypt.py with file/--env/--force args, registered as env-manager-encrypt console_script in pyproject.toml, with subprocess integration tests for both module and script invocation.

## Objective

Wire the CLI entry point by adding an argparse-based `main()` function to `encrypt.py` and registering `env-manager-encrypt` as a console_script in `pyproject.toml`. Makes the encryption function accessible as a command-line tool via both `python -m env_manager.cli.encrypt` and the `env-manager-encrypt` registered script.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add argparse main() to encrypt.py and register in pyproject.toml | 5893b42 | src/env_manager/cli/encrypt.py, pyproject.toml |
| 2 | Add TestCLIEntryPoint tests and run full test suite | 7e1b405 | tests/test_cli_encrypt.py |

## Verification Results

- `uv run python -m env_manager.cli.encrypt --help` — exits 0, shows env-manager-encrypt usage
- `uv run env-manager-encrypt --help` — exits 0, shows --force flag
- `uv run pytest tests/test_cli_encrypt.py -v` — 20/20 tests pass (16 from plan 01 + 4 new)
- `uv run pytest tests/ --ignore=tests/smoke` — 127 passed, 11 pre-existing failures (unchanged from before this plan)

## Deviations from Plan

### Out-of-scope Pre-existing Failures

**Pre-existing 11 test failures** (confirmed pre-existing before Task 1 via git stash):
- `tests/test_end_to_end.py::test_mixed_sources_load_in_one_eager_pass` — mock signature mismatch from Phase 02
- 5 tests in `tests/test_environment_integration.py::TestEnvironmentSelection`
- 4 tests in `tests/test_resolution_pipeline.py`
- 1 test in `tests/test_resolution_validation.py`

These were all pre-existing before this plan and are deferred technical debt from Phase 02 (APP_ENV rename regression). No new failures introduced.

## Known Stubs

None — `main()` is fully wired to `encrypt_dotenv_file()`. Entry point registered and verified working.

## Self-Check: PASSED
