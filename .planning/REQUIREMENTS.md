# Requirements: env-manager v2

**Defined:** 2026-03-06
**Core Value:** Developers declare config variables once in YAML and the library resolves them from the correct source for the active environment

## v1 Requirements

### Environment Configuration

- [x] **ENV-01**: YAML config supports an `environments:` section defining named environments with `origin`, `dotenv_path`, and `gcp_project_id` per environment
- [x] **ENV-02**: Active environment is selected via `ENVIRONMENT` env var, falling back to `default` if not set
- [x] **ENV-03**: Each environment config determines which loader (local/gcp) and which .env file path to use
- [x] **ENV-04**: `dotenv_path` in environment config accepts a full path or a filename resolved relative to project root

### Backwards Compatibility

- [x] **COMPAT-01**: Old YAML format without `environments:` section continues to work by auto-creating a `default` environment from existing settings
- [x] **COMPAT-02**: `init_config()` and `get_config()` / `require_config()` signatures remain compatible with existing consumers

### Variable Resolution

- [x] **RESOLVE-01**: Variable value resolution order is: os.environ > .env file (from active environment config) > YAML default
- [x] **RESOLVE-02**: Variables with only a `default` and no `source` skip the loader entirely with no warnings
- [x] **RESOLVE-03**: Variables with a `source` that aren't found follow existing required/optional/strict validation rules

### Per-Variable Overrides

- [x] **OVERRIDE-01**: A variable can specify `origin:` to override the active environment's origin (e.g., load from gcp while active env is local)
- [x] **OVERRIDE-02**: A variable can specify `dotenv_path:` to override the active environment's .env path when origin is local
- [x] **OVERRIDE-03**: A variable can specify `environment:` to pin it to a specific named environment (uses that env's origin and dotenv_path)
- [x] **OVERRIDE-04**: A variable can combine `origin:` and `dotenv_path:` to fully override source independently of any environment

## v2 Requirements

### Extended Loaders

- **LOAD-01**: AWS Secrets Manager loader
- **LOAD-02**: HashiCorp Vault loader

### Advanced Features

- **ADV-01**: Multi-file YAML config (split config across files)
- **ADV-02**: Config hot-reload at runtime

## Out of Scope

| Feature | Reason |
|---------|--------|
| Docker environment detection | Docker Compose env vars already in os.environ, handled by existing flow |
| Environment selection via init_config() param | ENVIRONMENT env var is sufficient; environment is infrastructure concern |
| New loader backends in v1 | Focus on core environment-aware architecture first |
| Hot-reloading | Not needed for current use cases |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Complete |
| ENV-02 | Phase 1 | Complete |
| ENV-03 | Phase 1 | Complete |
| ENV-04 | Phase 1 | Complete |
| COMPAT-01 | Phase 1 | Complete |
| COMPAT-02 | Phase 1 | Complete |
| RESOLVE-01 | Phase 2 | Complete |
| RESOLVE-02 | Phase 2 | Complete |
| RESOLVE-03 | Phase 2 | Complete |
| OVERRIDE-01 | Phase 3 | Complete |
| OVERRIDE-02 | Phase 3 | Complete |
| OVERRIDE-03 | Phase 3 | Complete |
| OVERRIDE-04 | Phase 3 | Complete |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-03-06*
*Last updated: 2026-03-06 after completing Phase 2*
