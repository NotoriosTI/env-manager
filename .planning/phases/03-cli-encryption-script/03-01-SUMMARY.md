---
phase: 03-cli-encryption-script
plan: "01"
subsystem: cli
tags: [encryption, ecies, secp256k1, dotenvx, cli, tdd]
dependency_graph:
  requires:
    - 02-encrypted-dotenv-support (DotEnvLoader with encrypted=True used for round-trip verification)
  provides:
    - encrypt_dotenv_file() function importable from env_manager.cli.encrypt
    - src/env_manager/cli/ package (new)
  affects:
    - tests/test_cli_encrypt.py (new)
tech_stack:
  added:
    - coincurve (secp256k1 key generation via PrivateKey)
    - eciespy (ECIES encryption via ecies.encrypt)
  patterns:
    - TDD RED-GREEN cycle with ImportError as RED state
    - Lazy import of crypto libs with helpful error message for missing [encrypted] extra
    - dotenv_values() for parsing, Path.write_text() for atomic file writes
key_files:
  created:
    - src/env_manager/cli/__init__.py
    - src/env_manager/cli/encrypt.py
    - tests/test_cli_encrypt.py
  modified: []
decisions:
  - "Lazy import of coincurve/ecies inside encrypt_dotenv_file to give helpful error when [encrypted] extra not installed"
  - "dotenv_values() used for parsing existing .env to avoid os.environ side-effects (consistent with Phase 02 pattern)"
  - "Pre-existing test failures (11 tests in test_end_to_end.py, test_environment_integration.py, test_resolution_pipeline.py, test_resolution_validation.py) confirmed as pre-existing before this plan — deferred to separate work item"
metrics:
  duration_seconds: 159
  completed_date: "2026-03-31"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
requirements:
  - CLI-01
  - CLI-02
  - CLI-03
  - CLI-04
  - CLI-05
  - CLI-06
  - CLI-07
---

# Phase 03 Plan 01: CLI Encrypt Core Function Summary

**One-liner:** secp256k1 ECIES encryption engine writing dotenvx-compatible `.env` + `.env.keys` via coincurve/eciespy with TDD coverage across all 7 CLI requirements.

## Objective

Implement `encrypt_dotenv_file()` in `src/env_manager/cli/encrypt.py` using TDD. The function generates a secp256k1 key pair, rewrites `.env` values as `encrypted:<base64>`, writes `DOTENV_PUBLIC_KEY` to the `.env` header, and outputs the private key to `.env.keys` in dotenvx format. Round-trip verification through `DotEnvLoader` proves crypto correctness.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create cli package marker and RED tests | 46a4bb3 | src/env_manager/cli/__init__.py, tests/test_cli_encrypt.py |
| 2 | Implement encrypt_dotenv_file (GREEN + REFACTOR) | 67630c3 | src/env_manager/cli/encrypt.py |

## Verification Results

- `uv run pytest tests/test_cli_encrypt.py -v` — 16/16 tests pass
- `uv run python -c "from env_manager.cli.encrypt import encrypt_dotenv_file; print('import OK')"` — import OK
- No regressions introduced (pre-existing failures confirmed pre-existing via git stash verification)

## Deviations from Plan

None — plan executed exactly as written. The implementation from the plan worked on the first attempt with all 16 tests passing immediately.

## Known Stubs

None — `encrypt_dotenv_file()` is fully wired and operational. No placeholder values or TODO stubs remain.

## Deferred Items

**Pre-existing test failures** (outside scope of this plan, confirmed pre-existing before Task 1 commit):
- `tests/test_end_to_end.py::test_mixed_sources_load_in_one_eager_pass` — TypeError: `recording_create_loader()` missing `encrypted` kwarg (test mock doesn't match updated `create_loader` signature from Phase 02)
- 5 tests in `tests/test_environment_integration.py::TestEnvironmentSelection`
- 4 tests in `tests/test_resolution_pipeline.py`
- 1 test in `tests/test_resolution_validation.py`

These failures existed before this plan and are tracked as pre-existing technical debt from Phase 02 integration.

## Self-Check: PASSED
