# Roadmap: env-manager v2

## Overview

Transform env-manager from a flat config loader into an environment-aware configuration library. Phase 1 introduces the YAML schema for named environments with full backwards compatibility. Phase 2 rewires variable resolution to respect the active environment. Phase 3 adds per-variable overrides for mixed-source configurations.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Environment Schema** - Named environments in YAML with backwards-compatible parsing (completed 2026-03-06)
- [x] **Phase 2: Resolution Pipeline** - Environment-aware variable resolution with correct precedence (completed 2026-03-06)
- [x] **Phase 3: Per-Variable Overrides** - Variable-level origin, dotenv_path, and environment pinning (completed 2026-03-06)

## Phase Details

### Phase 1: Environment Schema
**Goal**: Developers can define named environments in YAML and the library correctly parses both new and legacy formats
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, ENV-03, ENV-04, COMPAT-01, COMPAT-02
**Success Criteria** (what must be TRUE):
  1. A YAML config with an `environments:` section loads without error, and each named environment exposes its origin, dotenv_path, and gcp_project_id
  2. Setting `ENVIRONMENT=staging` selects the `staging` environment; omitting it falls back to `default`
  3. An existing YAML config without `environments:` continues to load and behave identically to current behavior
  4. `init_config()`, `get_config()`, and `require_config()` work with both old and new YAML formats without signature changes
**Plans:** 2/2 plans complete

Plans:
- [x] 01-01-PLAN.md — EnvironmentConfig dataclass and parse_environments parser with validation
- [x] 01-02-PLAN.md — Wire environment selection into ConfigManager with backwards compatibility

### Phase 2: Resolution Pipeline
**Goal**: Variables resolve from the correct source based on the active environment's configuration
**Depends on**: Phase 1
**Requirements**: RESOLVE-01, RESOLVE-02, RESOLVE-03
**Success Criteria** (what must be TRUE):
  1. A variable present in os.environ takes that value regardless of .env file or YAML default
  2. A variable absent from os.environ but present in the active environment's .env file takes the .env value
  3. A variable with only a YAML `default` and no `source` resolves to the default without triggering a loader or producing warnings
  4. A required variable missing from all sources raises a validation error; an optional variable missing resolves to None or its default
**Plans**: 2/2 plans complete

Plans:
- [x] 02-01-PLAN.md — Core sourced precedence and default-only variable bypass
- [x] 02-02-PLAN.md — Missing-source diagnostics and explicit active-environment `.env` contract

### Phase 3: Per-Variable Overrides
**Goal**: Individual variables can override their source independently of the active environment
**Depends on**: Phase 2
**Requirements**: OVERRIDE-01, OVERRIDE-02, OVERRIDE-03, OVERRIDE-04
**Success Criteria** (what must be TRUE):
  1. A variable with `origin: gcp` loads from GCP Secret Manager even when the active environment's origin is `local`
  2. A variable with `dotenv_path: .env.secrets` loads from that specific file instead of the environment's default .env path
  3. A variable with `environment: production` uses the `production` environment's origin and dotenv_path regardless of the active environment
  4. A variable combining `origin: local` and `dotenv_path: .env.special` loads from that file independent of any environment config
**Plans**: 2/2 plans complete

Plans:
- [x] 03-01-PLAN.md — Per-variable environment and origin override context
- [x] 03-02-PLAN.md — Per-variable dotenv-path overrides and mixed-context execution

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Environment Schema | 2/2 | Complete   | 2026-03-06 |
| 2. Resolution Pipeline | 2/2 | Complete | 2026-03-06 |
| 3. Per-Variable Overrides | 2/2 | Complete | 2026-03-06 |
| 4. Comprehensive Testing | 1/1 | Complete | 2026-03-11 |
| 5. Reduce and Consolidate | 3/3 | Complete | 2026-03-11 |

### Phase 4: Comprehensive testing and validation suite

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 3
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 4 to break down)

### Phase 5: Reduce and consolidate test suite

**Goal:** Remove redundant tests and consolidate helpers to slim the test suite without losing coverage
**Requirements**: TBD
**Depends on:** Phase 4
**Plans:** 3/3 plans complete

Plans:
- [x] 05-01-PLAN.md — Slim test_validation.py: remove 2 redundant tests, replace local helper (completed 2026-03-11)
- [x] 05-02-PLAN.md — Slim test_secret_origin_detection.py: keep 1 unique test, remove 3 redundant (completed 2026-03-11)
- [x] 05-03-PLAN.md — Slim test_bool_to_string_coercion.py: collapse 5 to 3 tests, modernise fixtures (completed 2026-03-11)
