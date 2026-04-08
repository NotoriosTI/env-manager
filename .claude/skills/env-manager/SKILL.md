---
name: env-manager
description: Interactive wizard to install, scaffold, or migrate projects to env-manager (Python or JS/TS)
---

# env-manager Setup Wizard

You are running an interactive setup wizard for the `env-manager` ecosystem. Guide the user step by step — ask one question at a time and wait for answers before proceeding.

---

## Phase 1 — Detect Project Language

Check for these files in the current working directory:

```bash
ls package.json pyproject.toml requirements.txt 2>/dev/null
```

**Decision logic:**
- `package.json` found, no Python files → **JS/TS** → use `@notoriosti/env-manager`
- `pyproject.toml` or `requirements.txt` found, no `package.json` → **Python** → use `env-manager`
- Both found → Ask: "I see both `package.json` and Python config files. Which language is this project primarily? (js / python)"
- Neither found → Ask: "I couldn't detect the project type. Is this a JavaScript/TypeScript or Python project? (js / python)"

**For Python projects, also detect the package manager:**
```bash
ls poetry.lock Pipfile .venv venv 2>/dev/null
# Also check pyproject.toml for [tool.poetry]
grep -l "tool.poetry" pyproject.toml 2>/dev/null
```
- `poetry.lock` found OR `[tool.poetry]` in `pyproject.toml` → use **poetry**
- `.venv/`, `venv/`, or `Pipfile` found → use **pip**
- None detected → Ask: "How are you managing your Python environment? (poetry / pip / conda / other)"

**Check if already installed:**
- JS/TS: `grep "@notoriosti/env-manager" package.json 2>/dev/null`
- Python/poetry: `grep "env-manager" pyproject.toml 2>/dev/null`
- Python/pip: `grep "env-manager" requirements.txt 2>/dev/null`

**Announce and confirm:**
```
Detected: [JS/TypeScript | Python] project
Package manager: [npm | poetry | pip]
Will use: [@notoriosti/env-manager | env-manager]
Already installed: [yes | no]

Proceed?
```

Wait for user confirmation before continuing.

---

## Phase 2 — Mode Selection

Ask:
```
Is this a new project or an existing one?

  1. New project — scaffold config from scratch
  2. Existing project — migrate from process.env / os.getenv() usage
```

---

## Phase 3 — Environment Configuration (Multi-Environment Builder)

This phase builds the `environments:` block interactively. The user defines one or more named environments, each backed by a different secret source. A common real-world setup is:
- `local` environment → plain `.env` (dev, no secrets stored in repo)
- `production` environment → GCP Secret Manager

### Step 3.1 — Explain the model

Tell the user:
```
env-manager supports named environments (e.g. "local", "staging", "production").
Each environment has its own secret source. The app picks the active one via the
ENVIRONMENT env var at runtime.

Let's define your environments one at a time. You can add as many as you need.
```

### Step 3.2 — Build environments interactively

Loop until the user says "done". For each environment:

**Ask for environment name:**
```
Environment name? (e.g. local, development, staging, production) [or "done" to finish]
```

**Ask for secret source:**
```
Secret source for "[name]"?

  1. local           — plain .env file
  2. local_encrypted — ECIES-encrypted .env (dotenvx-compatible)
  3. gcp             — GCP Secret Manager

  Or describe your setup (e.g. "plain .env for dev, GCP for prod"):
```

Accept free-form answers and map them:
- "plain", "local", ".env", "dotenv", "dev" → `local`
- "encrypted", "encrypt", "ecies", "dotenvx" → `local_encrypted`
- "gcp", "google", "secret manager", "cloud" → `gcp`
- Anything unclear → ask a follow-up clarifying question

**Ask if this is the default environment** (only for the first environment, or if none has been marked default yet):
```
Should "[name]" be the default environment when ENVIRONMENT is not set? (yes / no)
```

**For `local` and `local_encrypted`: ask for dotenv path**
```
Path to .env file for "[name]"? [default: .env]
```

**For `gcp`: ask for GCP project ID**
```
GCP project ID for "[name]"? (e.g. my-project-123)
```
If user doesn't know yet, accept `YOUR_GCP_PROJECT_ID` as placeholder.

**After each environment, ask:**
```
Add another environment? (yes / no)
```

### Step 3.3 — Summarize and confirm

After collecting all environments, show the summary:
```
Here are the environments you've defined:

  local       → local plain .env at .env (default)
  production  → GCP Secret Manager (project: my-project-123)

Does this look right? (yes / edit / no)
```

### Derived flags (used in later phases)

After Phase 3 completes, determine:
- `$HAS_ENCRYPTED` — true if any environment uses `local_encrypted`
- `$HAS_GCP` — true if any environment uses `gcp`
- `$ENVIRONMENTS` — list of all defined environment configs

These flags drive installation extras, `.gitignore` updates, and Phase 5/6 setup.

---

## Phase 4A — New Project Scaffold

### Install Package

**JS/TS:**
```bash
npm install @notoriosti/env-manager
```

**Python/poetry — no encryption needed (`$HAS_ENCRYPTED` is false):**
```bash
poetry add "env-manager @ git+https://github.com/NotoriosTI/env-manager.git@main"
```

**Python/poetry — encryption needed (`$HAS_ENCRYPTED` is true — auto-adds eciespy + coincurve):**
```bash
poetry add "env-manager[encrypted] @ git+https://github.com/NotoriosTI/env-manager.git@main"
```

**Python/pip — no encryption:**
```bash
pip install git+https://github.com/NotoriosTI/env-manager.git@main
```

**Python/pip — encryption needed:**
```bash
pip install "env-manager[encrypted] @ git+https://github.com/NotoriosTI/env-manager.git@main"
```

> Note: The `[encrypted]` extra is selected automatically based on whether any environment in `$ENVIRONMENTS` uses `local_encrypted`. No extra question needed.

Skip installation if already installed (detected in Phase 1).

### Generate config.yaml

Write `config.yaml` (or `config/config_vars.yaml` — ask user for preferred path, default `config.yaml`).

Build the `environments:` block dynamically from `$ENVIRONMENTS` collected in Phase 3. For each defined environment, emit the correct block:

**`local` environment block:**
```yaml
  <name>:
    origin: local
    dotenv_path: <dotenv_path>   # e.g. .env
    default: true                # only on the default environment
```

**`local_encrypted` environment block:**
```yaml
  <name>:
    origin: local
    dotenv_path: <dotenv_path>
    default: true                # only on the default environment
    encrypted_dotenv:
      enabled: true
```

**`gcp` environment block:**
```yaml
  <name>:
    origin: gcp
    gcp_project_id: <gcp_project_id>
    default: true                # only if marked default
```

**Example — local plain + GCP (common dev/prod setup):**
```yaml
environments:
  local:
    origin: local
    dotenv_path: .env
    default: true
  production:
    origin: gcp
    gcp_project_id: my-project-123
```

**Example — local encrypted + GCP:**
```yaml
environments:
  local:
    origin: local
    dotenv_path: .env
    default: true
    encrypted_dotenv:
      enabled: true
  production:
    origin: gcp
    gcp_project_id: my-project-123
```

**Example — three environments (dev plain, staging encrypted, prod GCP):**
```yaml
environments:
  development:
    origin: local
    dotenv_path: .env
    default: true
  staging:
    origin: local
    dotenv_path: .env.staging
    encrypted_dotenv:
      enabled: true
  production:
    origin: gcp
    gcp_project_id: my-project-123
```

After the `environments:` block, always append the `variables:` and `validation:` scaffolds:

```yaml
variables:
  EXAMPLE_KEY:
    source: EXAMPLE_KEY
    type: str
    required: true
  PORT:
    source: PORT
    type: int
    default: 8080

validation:
  strict: false
  required:
    - EXAMPLE_KEY
  optional:
    - PORT
```

Show the full generated file to the user and ask for confirmation before writing.

### Create .env.example

```bash
# .env.example — copy to .env and fill in real values
EXAMPLE_KEY=your-value-here
PORT=8080
```

### Update .gitignore (if encrypted)

If `$HAS_ENCRYPTED` is true (any environment uses `local_encrypted`), append to `.gitignore`:
```
.env.keys
```

Check first with `grep ".env.keys" .gitignore` to avoid duplicates.

### Inject init snippet

Ask: "Where should I inject the `initConfig` call? (Press enter for default)"
- Python default: `__init__.py` at package root (find with `find . -name "__init__.py" -maxdepth 3 | head -5`)
- JS/TS default: detect entry point — look for `index.ts`, `app.ts`, `server.ts`, `main.ts` in `src/` or root

**Python snippet (inject near top, after existing imports):**
```python
from env_manager import init_config, get_config, require_config

init_config("config.yaml")
```

**JS/TS snippet (inject at top of async main function or module top-level):**
```ts
import { initConfig, getConfig, requireConfig } from '@notoriosti/env-manager';

await initConfig('./config.yaml');
```

Show the user what will be written and ask: "Inject this snippet into `[file]`? (yes / no / enter different path)"

---

## Phase 4B — Existing Project Migration

### Scan .env Files

```bash
# Find all .env files (excluding keys and examples)
find . -name ".env*" \
  ! -name ".env.keys" \
  ! -name ".env.example" \
  ! -path "*/node_modules/*" \
  ! -path "*/.git/*" \
  2>/dev/null
```

### Parse Variable Names

For each found `.env` file, extract key names:
```bash
grep -h "^[A-Z_][A-Z0-9_]*=" <found-files> | cut -d= -f1 | sort -u
```

### Generate config.yaml from discovered keys

Build a `config.yaml` with all discovered variables listed under `variables:`. Default each to:
- `type: str`
- `required: true` if the key appears in `.env.example`, else `required: false`
- No `default` value (leave for user to set)

Show the user a preview of the generated `config.yaml` and ask: "Write this config.yaml? (yes / edit first / no)"

### Install Package

Same logic as Phase 4A — install only if not already present.

### Determine init_config placement

Same as Phase 4A — ask for file, show default, inject on confirmation.

### Show migration snippets

After writing config, scan for raw env access patterns:

**JS/TS:**
```bash
grep -rn "process\.env\." --include="*.ts" --include="*.js" . | grep -v node_modules
```

**Python:**
```bash
grep -rn "os\.getenv\|os\.environ\[" --include="*.py" . | grep -v ".venv" | grep -v "venv/"
```

Show the user the list of files with raw access. Then show migration example:

**Before (JS/TS):**
```ts
const dbPass = process.env.DB_PASSWORD;
```
**After:**
```ts
const dbPass = getConfig('DB_PASSWORD') as string;
```

**Before (Python):**
```python
db_pass = os.getenv("DB_PASSWORD")
```
**After:**
```python
db_pass = get_config("DB_PASSWORD")
```

Ask: "Would you like me to automatically replace these usages? (yes / no)"

If yes — replace each occurrence. If no — show the list so the user can migrate manually.

---

## Phase 5 — Encryption Setup

*Only run if `$HAS_ENCRYPTED` is true (at least one environment uses `local_encrypted`).*

**JS/TS:**
```bash
npx env-manager-encrypt .env
```

**Python:**
```bash
env-manager-encrypt .env
```

After running:
1. Confirm `.env.keys` was created: `ls -la .env.keys`
2. Confirm `.env.keys` is in `.gitignore`: `grep ".env.keys" .gitignore`
3. Show CI/CD guidance:

```
To use encrypted secrets in CI/CD:
  1. Copy the key from .env.keys
  2. Add it as a CI secret: DOTENV_PRIVATE_KEY
  3. The app will automatically decrypt at runtime
```

---

## Phase 6 — GCP Setup

*Only run if `$HAS_GCP` is true (at least one environment uses `gcp`).*

Ask: "What is your GCP project ID?"

Update `config.yaml` to replace `YOUR_GCP_PROJECT_ID` with the provided value.

Then show:
```
Grant Secret Manager access to your service account:

  gcloud projects add-iam-policy-binding YOUR_GCP_PROJECT_ID \
    --member="serviceAccount:YOUR_SA@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

To push a secret to GCP:

  echo -n "my-secret-value" | \
    gcloud secrets create MY_KEY --data-file=- --project=YOUR_GCP_PROJECT_ID
  
  # Or update existing:
  echo -n "my-secret-value" | \
    gcloud secrets versions add MY_KEY --data-file=- --project=YOUR_GCP_PROJECT_ID
```

---

## Phase 7 — Optional Follow-ups

Ask after setup completes:

```
Setup complete! Would you like to:

  1. Add more variables interactively
  2. Audit config vs .env (report missing or extra keys)
  3. Done
```

**Option 1 — Add variables:**
Loop:
- Ask: "Variable name?"
- Ask: "Type? (str / int / float / bool)"
- Ask: "Required? (yes / no)"
- Ask: "Default value? (press enter to skip)"
- Ask: "Source name in .env/GCP? (press enter to use same as variable name)"
- Append to `config.yaml` variables section
- Ask: "Add another? (yes / no)"

**Option 2 — Audit:**
```bash
# Extract keys from config.yaml
grep -A1 "^variables:" config.yaml | grep "^  [A-Z]" | awk -F: '{print $1}' | xargs

# Extract keys from .env
grep -h "^[A-Z_][A-Z0-9_]*=" .env 2>/dev/null | cut -d= -f1 | sort
```

Compare and report:
- Keys in `.env` but missing from `config.yaml` → "Not tracked in config"
- Keys in `config.yaml` but missing from `.env` → "Missing from .env"
- Keys in both → OK

---

## Reference: config.yaml Full Schema

```yaml
environments:
  default:
    origin: local          # local | gcp
    dotenv_path: .env
    default: true
    encrypted_dotenv:      # optional — for encrypted local
      enabled: true
  gcp:
    origin: gcp
    gcp_project_id: my-project-id

variables:
  KEY_NAME:
    source: KEY_NAME       # name in .env or GCP (default: same as key)
    type: str              # str | int | float | bool
    required: true
    default: fallback      # optional fallback if not found

validation:
  strict: false            # true = fail on any unknown key
  required:
    - KEY_NAME
  optional:
    - DEBUG_MODE
```

## Reference: JS/TS API

```ts
import { initConfig, getConfig, requireConfig } from '@notoriosti/env-manager';

// Call once at startup — always await
await initConfig('./config.yaml');

// Synchronous after init
const port = getConfig('PORT') as number;          // returns undefined if missing
const secret = requireConfig('JWT_SECRET') as string; // throws if missing
```

## Reference: Python API

```python
from env_manager import init_config, get_config, require_config

# Call once at startup
init_config("config.yaml")

# Synchronous after init
port = get_config("PORT", 8080)       # returns default if missing
secret = require_config("JWT_SECRET") # raises if missing
```

## Reference: CLI Commands

**JS/TS:**
```bash
npx env-manager-encrypt .env              # encrypt .env → .env (in-place), keys → .env.keys
npx env-manager-encrypt .env --env prod  # encrypt into named environment slot
npx env-manager-encrypt .env --force     # overwrite existing encrypted file
```

**Python:**
```bash
env-manager-encrypt .env
env-manager-encrypt .env --env prod
env-manager-encrypt .env --force
```
