# Roadmap: env-manager (Python)
Created: 2026-03-31
Last updated: 2026-03-31

## TS Reference (Always Consult First)

**The TypeScript repo (`../env-manager-js`) is the primary reference for all feature behavior, logic, and edge cases in this milestone.** When planning or implementing any phase, read the corresponding TS phase plans and source before writing Python code. If behavior is unclear, look at the TS tests — they are the behavioral specification.

| Python Phase | TS Equivalent | TS Plan directory |
|-------------|---------------|------------------|
| 01 — Validation Diagnostics | TS Phase 02 | `../env-manager-js/.planning/phases/02-*/` |
| 02 — Encrypted Dotenv Support | TS Phase 03 | `../env-manager-js/.planning/phases/03-*/` |
| 03 — CLI Encryption Script | TS Phase 03.1 | `../env-manager-js/.planning/phases/03.1-*/` |
| 04 — Generic Typed Retrieval | TS Phase 04 | `../env-manager-js/.planning/ROADMAP.md` (not yet executed in TS) |
| 05 — Schema-Safe Config Access | TS Phase 05 | `../env-manager-js/.planning/ROADMAP.md` (not yet executed in TS) |
| 06 — Runtime Ergonomics | TS Phase 06 | `../env-manager-js/.planning/ROADMAP.md` (not yet executed in TS) |

Document any intentional Python divergence explicitly in the phase plan before implementing.

## Overview

Python `env-manager` Milestone 2 (`v0.2.0`) brings the library to parity with the TypeScript port's `v0.2.0` milestone. Phases cover validation diagnostics, encrypted dotenv handling, CLI encryption tooling, typed access patterns, and runtime ergonomics — all as opt-in additions that preserve existing default behavior.

## Milestones

- ✅ **v1.0 Initial Release** — Core Python library (DotEnvLoader, GCPSecretLoader, ConfigManager, singleton) — shipped prior to 2026-03-31
- 🚧 **v0.2.0 / Milestone 2** — Phases 01-06 — in progress

## Current State

- Active milestone: **v0.2.0 / Milestone 2**
- Milestone goal: Port the six TS v0.2.0 backlog items to Python, preserving `None` semantics, opt-in defaults, and existing call-site behavior
- Sequence: validation diagnostics first, then encrypted dotenv + CLI, then validator-agnostic typed retrieval, then schema-safe accessors, then logger injection and dotenv expansion

## Phases

- [x] **Phase 01: Validation Diagnostics** - Aggregate `load()` validation failures into one exported `ConfigValidationError` without changing existing strictness behavior. (pending) (completed 2026-03-31)
- [x] **Phase 02: Encrypted Dotenv Support** - Add opt-in dotenvx-compatible encrypted value decryption with explicit key resolution and error typing. (pending) (completed 2026-03-31)
- [ ] **Phase 03: CLI Encryption Script** - Add `env-manager-encrypt` console_script to encrypt dotenv files with automatic key management. (pending)
- [ ] **Phase 04: Generic Typed Retrieval** - Add typed `get_config[T]` and `require_config[T]` overloads with optional validator-backed parsing while preserving existing callers. (pending)
- [ ] **Phase 05: Schema-Safe Config Access** - Add `create_typed_config(schema)` for compile-time key safety on top of a validator-agnostic typed retrieval foundation. (pending)
- [ ] **Phase 06: Runtime Ergonomics** - Add injectable logger support and opt-in dotenv expansion without changing defaults for existing consumers. (pending)

## Phase Details

### Phase 01: Validation Diagnostics
**Goal**: Users see every missing or invalid required configuration issue from a load attempt in one exported `ConfigValidationError`.
**Depends on**: v1.0 baseline
**Requirements**: VAL-01, VAL-02, VAL-03, VAL-04
**Success Criteria** (what must be TRUE):
  1. User receives one `ConfigValidationError` from `load()` listing all missing required variables found in the current load attempt.
  2. User receives one `ConfigValidationError` from `load()` listing all invalid configured values found in the current load attempt instead of failing on the first invalid entry.
  3. Consumer can `isinstance`-check the exported `ConfigValidationError` class while existing `strict` and `required` semantics remain unchanged.
  4. A failed `load()` that raised `ConfigValidationError` can be retried — state is not permanently corrupted.
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Create ConfigValidationError types, public export, and failing regression tests for aggregate validation and retry safety
- [x] 01-02-PLAN.md — Refactor load() to aggregate fatal issues into ConfigValidationError and pass all regression tests

### Phase 02: Encrypted Dotenv Support
**Goal**: Users can opt into encrypted dotenv values with dotenvx-compatible decryption, configurable private-key lookup, and explicit failure behavior.
**Depends on**: Phase 01
**Requirements**: ENC-01, ENC-02, ENC-03, ENC-04, ENC-05, ENC-06
**Success Criteria** (what must be TRUE):
  1. User can enable encrypted dotenv handling per environment and plaintext environments keep their current behavior by default.
  2. User can load dotenvx-compatible `encrypted:` values from `.env` files when a matching private key is available.
  3. User receives an exported `DecryptionError` when encrypted values cannot be decrypted because the private key is missing or invalid.
  4. User can provide decryption keys through `DOTENV_PRIVATE_KEY_<ENV>`, then `DOTENV_PRIVATE_KEY`, then a colocated `.env.keys` file in that resolution order.
  5. User can configure the private-key secret name instead of being limited to `DOTENV_PRIVATE_KEY`.
  6. User can load the private decryption key from local dotenv-backed sources or GCP Secret Manager in addition to direct environment variable injection.
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Add failing regressions for encrypted dotenv loader behavior, manager opt-in activation, dedicated key sources, and the public decryption contract
- [x] 02-02-PLAN.md — Add exported `DecryptionError`/types and implement dotenvx-compatible loader decryption with lazy private-key lookup
- [x] 02-03-PLAN.md — Wire encrypted dotenv config through environment/manager resolution and close the phase with the regression gate

### Phase 03: CLI Encryption Script
**Goal**: Users can encrypt plaintext `.env` files into dotenvx-compatible encrypted format with automatic key pair generation and `.env.keys` file output.
**Depends on**: Phase 02
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07, CLI-08, CLI-09
**Success Criteria** (what must be TRUE):
  1. `env-manager-encrypt <file>` generates a secp256k1 key pair, writes `DOTENV_PUBLIC_KEY` into the target `.env`, and outputs a matching `.env.keys` file.
  2. All plaintext values in the target `.env` are rewritten as `encrypted:<base64>` ciphertext that decrypts back to the original value.
  3. Already-encrypted values and `DOTENV_PUBLIC_KEY` itself are skipped without modification.
  4. The command refuses to overwrite an existing `.env.keys` file unless `--force` is passed.
  5. Encrypted output round-trips through `DotEnvLoader` with `encrypted: true` and the matching private key.
  6. CLI entry point is registered as `env-manager-encrypt` in `pyproject.toml [project.scripts]`.
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — Implement core encryption module with TDD tests for key generation, value encryption, round-trip verification, and edge cases
- [ ] 03-02-PLAN.md — Wire CLI entry point with argparse, pyproject.toml script registration, and package install verification

### Phase 04: Generic Typed Retrieval
**Goal**: Consumers can opt into typed config reads and validator-backed retrieval without breaking existing untyped access patterns.
**Depends on**: Phase 03
**Requirements**: TYPE-01, TYPE-02
**Success Criteria** (what must be TRUE):
  1. Consumer can call `get_config("name", type_=int)` / `require_config("name", type_=str)` with type parameters and existing untyped call sites continue to behave the same way.
  2. Consumer can pass a validator callable or object with a `parse` method to `get_config` or `require_config` and receive a validated typed result without the public API requiring Pydantic or another specific library.
  3. Typed retrieval continues to preserve the existing missing-value and required-value runtime contract for callers that opt in.
  4. Type stubs / `@overload` declarations allow mypy/pyright to infer the return type without runtime overhead.
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

### Phase 05: Schema-Safe Config Access
**Goal**: Consumers can create a schema-defined config accessor that enforces key safety at type-check time without coupling the API to one validator vendor.
**Depends on**: Phase 04
**Requirements**: TYPE-03
**Success Criteria** (what must be TRUE):
  1. Consumer can create a typed accessor with `create_typed_config(schema)` and retrieve only keys declared in that schema.
  2. Consumer gets mypy/pyright errors for keys outside the declared schema when using the typed accessor.
  3. Values returned from the typed accessor are typed from the declared schema instead of requiring manual casts.
  4. The accessor API remains validator-agnostic so Pydantic can be the first documented adapter rather than the only supported contract.
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 06: Runtime Ergonomics
**Goal**: Consumers can integrate library logging and dotenv interpolation into their own runtime conventions without changing default behavior.
**Depends on**: Phase 05
**Requirements**: OBS-01, OBS-02, EXP-01
**Success Criteria** (what must be TRUE):
  1. Consumer can inject a logger through `ConfigManagerOptions` so runtime warnings and logs no longer require the module-level `logging` logger.
  2. Consumer can rely on an exported `LoggerProtocol` that requires `warning` and `info` and supports optional `debug` and `error` methods.
  3. User can opt into dotenv interpolation and the default disabled behavior remains unchanged when expansion is not enabled.
**Plans**: TBD

Plans:
- [ ] 06-01: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01. Validation Diagnostics | 0/2 | Not started | - |
| 02. Encrypted Dotenv Support | 0/3 | Not started | - |
| 03. CLI Encryption Script | 0/2 | Not started | - |
| 04. Generic Typed Retrieval | 0/TBD | Not started | - |
| 05. Schema-Safe Config Access | 0/TBD | Not started | - |
| 06. Runtime Ergonomics | 0/TBD | Not started | - |

## Backlog

### Phase 999.1: Implementation of encrypted variable loading from non-local origin (BACKLOG)

**Goal:** Implement encrypted dotenv decryption support for non-local origins (e.g. GCP Secret Manager), adding a `NotImplementedError` guard in Phase 02 until this is ready.
**Requirements:** TBD
**Plans:** 1/2 plans executed

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)

### Phase 999.2: GCP secret version fallback when latest key is destroyed (BACKLOG)

**Goal:** When the latest version of a GCP secret is destroyed, fall back to the most recent accessible version instead of failing. Verify whether the same fallback gap exists for regular (non-encrypted) variable loading from GCP.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)
