# env-manager

A Python 3.13+ configuration manager that unifies secrets from local `.env` files and Google Cloud Secret Manager. Handles type coercion, validation, secret masking, optional ECIES encryption, and automatically populates `os.environ` so external libraries work without extra setup.

## Installation

```bash
# uv
uv add notoriosti-env-manager

# Poetry
poetry add notoriosti-env-manager
```

For encrypted `.env` file support:

```bash
uv add "notoriosti-env-manager[encrypted]"
poetry add "notoriosti-env-manager[encrypted]"
```

## Quickstart

Initialize once at startup, use anywhere:

```python
from env_manager import init_config, get_config

init_config("config/config_vars.yaml")

db_password = get_config("DB_PASSWORD")
api_timeout = get_config("API_TIMEOUT", 30)  # with default
```

**What happens automatically:**
- Secrets are fetched from `.env` or GCP Secret Manager
- Types are coerced per YAML definitions (`str`, `int`, `float`, `bool`)
- Required/optional validation runs and logs warnings or raises errors
- All values are written to `os.environ` as strings
- Secrets are masked in all log output

## Configuration File

```yaml
# Optional: named environments, selected via ENVIRONMENT env var
environments:
  production:
    origin: gcp
    gcp_project_id: my-gcp-project
  local:
    origin: local
    dotenv_path: .env
    default: true  # used when ENVIRONMENT is not set

  # With encrypted .env support
  staging:
    origin: local
    dotenv_path: .env.staging
    encrypted_dotenv:
      enabled: true
      private_key:                       # optional — omit to use env vars or .env.keys
        source: DOTENV_PRIVATE_KEY       # secret name containing the hex private key
        secret_origin: gcp              # 'local' or 'gcp'
        gcp_project_id: my-gcp-project

variables:
  DB_PASSWORD:
    source: DB_PASSWORD   # name in .env or GCP Secret Manager
    type: str

  PORT:
    source: PORT
    type: int
    default: 8080

  LOG_LEVEL:
    type: str
    default: "INFO"   # constant — no external source needed

  ANALYTICS_KEY:
    source: ANALYTICS_KEY
    type: str
    origin: gcp                      # per-variable origin override
    dotenv_path: secrets/.env.gcp   # per-variable custom .env path

validation:
  strict: false    # true → all variables must resolve (ignores defaults)
  required:
    - DB_PASSWORD  # raises ConfigValidationError if missing
  optional:
    - DEBUG_MODE   # logs warning if missing
```

### Variable fields

| Field | Description |
|---|---|
| `source` | Name in `.env` or GCP Secret Manager |
| `type` | `str` (default), `int`, `float`, `bool` |
| `default` | Fallback value if not found |
| `origin` | `"local"` or `"gcp"` — overrides global secret origin for this variable |
| `dotenv_path` | Custom `.env` path for this variable |
| `environment` | Named environment to use as source context |

Each variable must have at least one of `source` or `default`.

**Boolean coercion** accepts only: `"true"`, `"True"`, `"1"`, `"false"`, `"False"`, `"0"`.

## Secret Origin Resolution

| Priority | Source |
|---|---|
| 1 | Explicit parameter: `init_config(..., secret_origin="gcp")` |
| 2 | `SECRET_ORIGIN` environment variable |
| 3 | `SECRET_ORIGIN=gcp` in `.env` file |
| 4 | Active environment's `origin` field |
| 5 | Default: `"local"` |

## GCP Project ID Resolution

| Priority | Source |
|---|---|
| 1 | Explicit parameter: `init_config(..., gcp_project_id="my-project")` |
| 2 | `GCP_PROJECT_ID` environment variable |
| 3 | `GCP_PROJECT_ID` in `.env` file |
| 4 | Active environment's `gcp_project_id` field |

## API Reference

### Singleton API (recommended)

```python
from env_manager import init_config, get_config, require_config

init_config(
    "config/config_vars.yaml",
    secret_origin=None,    # "local" or "gcp" — auto-detected if None
    gcp_project_id=None,   # required when secret_origin="gcp"
    strict=None,           # overrides YAML strict setting
    dotenv_path=None,      # custom .env path — auto-detected if None
    debug=False,           # log raw secret values (never use in production)
)

get_config("KEY")             # typed value or None
get_config("KEY", "default")  # typed value or provided default
require_config("KEY")         # typed value or raises RuntimeError
```

### Instance API

For multiple configs, dependency injection, or testing:

```python
from env_manager import ConfigManager

manager = ConfigManager(
    config_path="config/config_vars.yaml",
    secret_origin=None,
    gcp_project_id=None,
    strict=None,
    auto_load=True,
    dotenv_path=None,
    debug=False,
)

manager.get("DB_PASSWORD")
manager.get("PORT", 8080)
manager.require("API_KEY")
manager.values              # dict of all loaded values
```

### Loader API

```python
from env_manager import create_loader

loader = create_loader("local", dotenv_path=".env")
loader = create_loader("gcp", gcp_project_id="my-project")

values = loader.get_many(["DB_PASSWORD", "API_KEY"])
# → {"DB_PASSWORD": "secret", "API_KEY": "key123"}
```

## Encrypted .env Files

env-manager supports dotenvx-compatible ECIES encryption (secp256k1 + AES-256-GCM). Encrypted files are safe to commit to source control.

**Requires the `[encrypted]` extra.**

### Encrypting a file

```bash
# Encrypt .env in-place; writes private key to .env.keys
env-manager-encrypt .env

# With an environment name (writes DOTENV_PRIVATE_KEY_PRODUCTION to .env.keys)
env-manager-encrypt .env --env production

# Overwrite existing .env.keys
env-manager-encrypt .env --force
```

After encryption, `.env` values become `encrypted:<base64>` blobs and `DOTENV_PUBLIC_KEY` is written into the file header. The private key is written to `.env.keys` (same directory).

### Decryption at load time

Decryption is automatic when enabled in config. Private key resolution order:

| Priority | Source |
|---|---|
| 1 | Explicit kwarg passed to `create_loader` |
| 2 | `DOTENV_PRIVATE_KEY_<ENV>` environment variable (when environment name is set) |
| 3 | `DOTENV_PRIVATE_KEY` environment variable |
| 4 | Colocated `.env.keys` file (same directory as `.env`) |

Enable via YAML:

```yaml
environments:
  production:
    origin: local
    dotenv_path: .env
    encrypted_dotenv:
      enabled: true
```

Or store the private key in GCP and let env-manager fetch it:

```yaml
environments:
  production:
    origin: local
    dotenv_path: .env
    encrypted_dotenv:
      enabled: true
      private_key:
        source: DOTENV_PRIVATE_KEY
        secret_origin: gcp
        gcp_project_id: my-gcp-project
```

> **Warning:** Never `source .env` in a shell when the file is encrypted. The shell assigns raw ciphertext strings — no decryption occurs.

### Exceptions

```python
from env_manager import DecryptionError, DecryptionIssue

try:
    init_config("config/config_vars.yaml")
except DecryptionError as exc:
    for issue in exc.issues:  # list[DecryptionIssue]
        print(issue.key, issue.message)
```

`ConfigValidationError` works the same way, with `issues: list[ConfigValidationIssue]` where each issue has `variable` and `message` fields.

## Secret Masking

All secrets are masked in logs:

- **Short secrets** (< 10 chars): `**********`
- **Long secrets**: `ab****1234` (first 2 + last 4 chars shown)

```python
init_config("config/config_vars.yaml", debug=True)  # shows raw values — never in production
```

## Migration from python-dotenv

**Before:**
```python
from dotenv import load_dotenv
import os

load_dotenv()
db_password = os.environ["DB_PASSWORD"]
port = int(os.environ.get("PORT", "8080"))
```

**After:**
```python
from env_manager import init_config, get_config

init_config("config/config_vars.yaml")
db_password = get_config("DB_PASSWORD")
port = get_config("PORT")  # already an int, default 8080 from YAML
```

## Troubleshooting

**`Configuration manager not initialised`** — call `init_config()` before `get_config()` or `require_config()`.

**`Missing GCP project ID`** — set `GCP_PROJECT_ID` via parameter, env var, or `.env`.

**`Type coercion failed`** — check the `type` field in YAML matches your value format. Booleans must be exactly `"true"`, `"false"`, `"1"`, or `"0"`.

**`Required variable not found`** — verify the secret exists in `.env` or GCP, the name matches the `source` field, and GCP credentials have access.

**`eciespy is required`** — install the encrypted extra: `uv add "notoriosti-env-manager[encrypted]"`.

**`FileExistsError: .env.keys already exists`** — use `env-manager-encrypt .env --force` to overwrite.

## Development

```bash
uv sync
pytest -v
pytest --cov=env_manager --cov-report=html
```

## Related Projects

**[env-manager-js](https://github.com/NotoriosTI/env-manager-js)** — TypeScript implementation with full feature parity. Both share the same YAML config format and secret resolution logic.

## License

Copyright (c) 2025 NotoriosTI. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, distribution, or use of this software, in whole or in part, is strictly prohibited.
