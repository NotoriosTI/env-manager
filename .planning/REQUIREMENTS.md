# Requirements: env-manager (Python)

**Defined:** 2026-03-31
**Core Value:** Correct, parity-preserved behavior with documented semantics — new features extend without changing the observable resolution contract.

## Milestone 2 Requirements

Requirements for milestone `v0.2.0 / Milestone 2`. All items are new — not present in the existing Python v1.0 codebase.

### Validation

- [x] **VAL-01**: User receives a single `ConfigValidationError` from `load()` listing every missing required variable discovered in the current load attempt
- [x] **VAL-02**: User receives a single `ConfigValidationError` from `load()` listing every invalid configured value discovered in the current load attempt
- [x] **VAL-03**: Consumer can `isinstance`-check the exported `ConfigValidationError` class without changing existing `strict` or `required` semantics
- [x] **VAL-04**: `load()` remains retry-safe — a failed load attempt that raised `ConfigValidationError` can be retried with a fresh `load()` call

### Encryption

- [x] **ENC-01**: User can opt into encrypted `.env` handling per environment configuration without changing behavior for plaintext environments
- [x] **ENC-02**: User can load dotenvx-compatible `encrypted:` values from `.env` files when a matching private key is available
- [x] **ENC-03**: User receives an exported `DecryptionError` when encrypted values cannot be decrypted because the private key is missing or invalid
- [x] **ENC-04**: User can supply decryption keys through `DOTENV_PRIVATE_KEY_<ENV>`, `DOTENV_PRIVATE_KEY`, or a colocated `.env.keys` file in that resolution order
- [x] **ENC-05**: User can configure which secret name should be read for the private decryption key instead of being limited to `DOTENV_PRIVATE_KEY`
- [x] **ENC-06**: User can load the private decryption key from local dotenv-backed sources or GCP Secret Manager, not only from process environment variables or `.env.keys`

### CLI Encryption

- [ ] **CLI-01**: `encrypt` command generates a secp256k1 key pair and writes `DOTENV_PUBLIC_KEY` to the target `.env` file
- [ ] **CLI-02**: `encrypt` command rewrites each plaintext value as `encrypted:<base64>` and the ciphertext decrypts back to the original value
- [ ] **CLI-03**: `encrypt` command writes the private key to a colocated `.env.keys` file in dotenvx format
- [ ] **CLI-04**: `encrypt` command skips values already prefixed with `encrypted:`
- [ ] **CLI-05**: `encrypt` command skips the `DOTENV_PUBLIC_KEY` variable itself (never encrypts the public key)
- [ ] **CLI-06**: `encrypt` command refuses when a `.env.keys` file already exists unless `--force` is passed
- [ ] **CLI-07**: Encrypted output round-trips through `DotEnvLoader` with `encrypted: true` and the matching private key
- [ ] **CLI-08**: User can invoke the encrypt command via `python -m env_manager.cli.encrypt <file>` or a registered `env-manager-encrypt` console_script
- [ ] **CLI-09**: The CLI entry point is registered in `pyproject.toml` `[project.scripts]` and included in the package

### Typed Access

- [ ] **TYPE-01**: Consumer can call `get_config(name, type_=T)` / `require_config(name, type_=T)` with type parameters without breaking existing untyped call sites
- [ ] **TYPE-02**: Consumer can pass a validator callable or object to `get_config` / `require_config` and receive a validated typed result without requiring a specific validation library
- [ ] **TYPE-03**: Consumer can create a typed accessor via `create_typed_config(schema)` and get mypy/pyright errors for keys outside the declared schema while keeping the public contract validator-agnostic

### Observability

- [ ] **OBS-01**: Consumer can inject a logger through `ConfigManagerOptions` so runtime warnings and logs do not require direct `print` or module-level `logging` usage
- [ ] **OBS-02**: Consumer can rely on exported logger typing (a `Protocol`) that supports `warning`, `info`, and optional `debug` / `error` methods

### Dotenv Expansion

- [ ] **EXP-01**: User can opt into `.env` variable interpolation through `python-dotenv`'s `interpolate` feature without changing the default disabled behavior

## Future Requirements

Deferred until after the current milestone lands.

### Encryption

- **ENC-07**: User can generate or rotate encrypted `.env` payloads via library APIs (not just CLI)

### Typed Access

- **TYPE-04**: First-class helpers for popular validator libraries (Pydantic, attrs) beyond the initial validator-agnostic schema path

### Providers

- **PROV-01**: User can load secrets from additional cloud providers beyond GCP (AWS SSM, Vault)

## Out of Scope

Explicitly excluded from milestone `v0.2.0 / Milestone 2`.

| Feature | Reason |
|---------|--------|
| Plaintext/env resolution behavior changes | Would break established Python parity guarantees |
| Mandatory validator dependency for all consumers | Typed schema support must remain opt-in to preserve current install surface |
| Browser runtime support | Library is Python/server-focused |
| Non-local origin encrypted loading (GCP+encrypted) | Tracked as Backlog 999.1 — scoped out of this milestone to keep focus |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VAL-01 | Phase 01 | Complete |
| VAL-02 | Phase 01 | Complete |
| VAL-03 | Phase 01 | Complete |
| VAL-04 | Phase 01 | Complete |
| ENC-01 | Phase 02 | Complete |
| ENC-02 | Phase 02 | Complete |
| ENC-03 | Phase 02 | Complete |
| ENC-04 | Phase 02 | Complete |
| ENC-05 | Phase 02 | Complete |
| ENC-06 | Phase 02 | Complete |
| CLI-01 | Phase 03 | Pending |
| CLI-02 | Phase 03 | Pending |
| CLI-03 | Phase 03 | Pending |
| CLI-04 | Phase 03 | Pending |
| CLI-05 | Phase 03 | Pending |
| CLI-06 | Phase 03 | Pending |
| CLI-07 | Phase 03 | Pending |
| CLI-08 | Phase 03 | Pending |
| CLI-09 | Phase 03 | Pending |
| TYPE-01 | Phase 04 | Pending |
| TYPE-02 | Phase 04 | Pending |
| TYPE-03 | Phase 05 | Pending |
| OBS-01 | Phase 06 | Pending |
| OBS-02 | Phase 06 | Pending |
| EXP-01 | Phase 06 | Pending |

**Coverage:**
- Milestone 2 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-31*
*Last updated: 2026-03-31 after Milestone 2 initialization (mirrored from TS v0.2.0, adapted for Python idioms)*
