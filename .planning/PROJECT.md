# env-manager v2: Environment-Aware Configuration

## What This Is

A Python library that loads and validates configuration variables from multiple sources (`.env` files, GCP Secret Manager, defaults) using a YAML-driven declaration. Used as an internal library across multiple microservices at NotoriosTI. This milestone adds environment-aware configuration, per-variable source overrides, and cleaner default handling.

## Core Value

Developers declare their config variables once in YAML and the library resolves them from the correct source for the active environment — no manual wiring, no missed secrets.

## Requirements

### Validated

- ✓ YAML-driven variable declaration with source, type, and default — existing
- ✓ DotEnvLoader loads from `.env` files — existing
- ✓ GCPSecretLoader loads from GCP Secret Manager — existing
- ✓ Factory pattern selects loader by `SECRET_ORIGIN` — existing
- ✓ Type coercion (str, int, float, bool) — existing
- ✓ Singleton access via `init_config()` / `get_config()` / `require_config()` — existing
- ✓ Strict mode and required/optional validation — existing
- ✓ Values mirrored to `os.environ` — existing

### Active

- [ ] Named environments in YAML (`environments:` section) with origin, dotenv_path, gcp_project_id per environment
- [ ] Active environment selected via `ENVIRONMENT` env var, falling back to `default` environment
- [ ] Backwards compatibility: old flat YAML format (no `environments:` section) auto-creates a `default` environment
- [ ] Revised variable value resolution order: os.environ > .env file (per env config) > YAML default
- [ ] Default-only variables (no `source`) skip the loader entirely — no warnings, no source lookup
- [ ] Per-variable `environment:` override to pin a variable to a specific named environment
- [ ] Per-variable `origin:` override to use a different loader than the active environment's origin
- [ ] Per-variable `dotenv_path:` override when origin is `local` (path or filename resolved relative to project root)
- [ ] Per-variable origin + dotenv_path combination (override source to local and point to a specific .env file)

### Out of Scope

- Docker environment detection — Docker Compose env vars already land in `os.environ`, handled by existing flow
- New loader backends (e.g., AWS Secrets Manager, HashiCorp Vault) — future work
- Multi-file YAML config (splitting config across files) — keep single file
- Hot-reloading of config at runtime — not needed

## Context

- This is a brownfield library already used in production across multiple services
- Current YAML schema has `variables:` and `validation:` top-level keys
- The `environments:` section is a new top-level key that must coexist with existing schema
- Current load order for secret origin resolution: param > os.environ > .env > default "local"
- The new model makes origin/dotenv_path part of environment configuration rather than global settings
- `SECRET_ORIGIN` and `GCP_PROJECT_ID` become properties of the environment config, not standalone params

## Constraints

- **Backwards compatibility**: Existing YAML configs without `environments:` must continue to work unchanged
- **Python compatibility**: Must work with Python 3.10+ (current target)
- **Dependencies**: No new external dependencies — only use existing (PyYAML, python-dotenv, google-cloud-secret-manager)
- **API stability**: `init_config()`, `get_config()`, `require_config()` signatures should remain compatible

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Named environments in YAML | Centralizes env config in one place, avoids scattered .env.* discovery logic | — Pending |
| ENVIRONMENT env var only (no init param) | Simpler API, environment is an infrastructure concern not an app concern | — Pending |
| os.environ > .env > default resolution | Shell/Docker env vars should override file-based config | — Pending |
| Default-only vars skip loader | Prevents false warnings for hardcoded/computed values | — Pending |
| Per-variable overrides (origin, dotenv_path, environment) | Flexible enough for mixed-source configs without separate YAML files | — Pending |

---
*Last updated: 2026-03-06 after initialization*
