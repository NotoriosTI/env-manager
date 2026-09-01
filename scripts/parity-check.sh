#!/usr/bin/env bash
#
# Gate de paridad env-manager (py) <-> env-manager-js.
#
# Idéntico byte a byte en los dos repos. Corre los cinco pasos de la sección
# "Gate" de PARITY.md y falla ruidoso al primero que no cierre. Sin reporte
# verde de este script no hay PR ni publicación.
#
# Uso:
#   scripts/parity-check.sh
#
# Ubica el repo hermano por variable de entorno o por convención de directorio:
#   ENV_MANAGER_PY=/ruta/a/env-manager
#   ENV_MANAGER_JS=/ruta/a/env-manager-js

set -euo pipefail

# §1.5.5: nada de silenciar errores de infraestructura. Si algo revienta acá,
# revienta fuerte y dice dónde.
trap 'echo "FALLO en la línea $LINENO" >&2' ERR

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$here/pyproject.toml" ]]; then
  PY_REPO="$here"
  JS_REPO="${ENV_MANAGER_JS:-$(dirname "$here")/env-manager-js}"
else
  JS_REPO="$here"
  PY_REPO="${ENV_MANAGER_PY:-$(dirname "$here")/env-manager}"
fi

for repo in "$PY_REPO" "$JS_REPO"; do
  if [[ ! -d "$repo" ]]; then
    echo "No encuentro el repo hermano en '$repo'." >&2
    echo "Define ENV_MANAGER_PY / ENV_MANAGER_JS y vuelve a correr." >&2
    exit 1
  fi
done

PYTHON_BIN="${PYTHON_BIN:-$PY_REPO/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3)"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

failures=0
step() { printf '\n=== %s ===\n' "$1"; }
ok()   { printf '  OK   %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }

echo "py: $PY_REPO"
echo "js: $JS_REPO"

# ---------------------------------------------------------------------------
step "1/5 Resolución del fixture canónico"

( cd "$JS_REPO" && npm run --silent build >/dev/null )

"$PYTHON_BIN" "$PY_REPO/tests/fixtures/parity/emit.py" > "$tmp/py.json" 2>"$tmp/py.err"
node "$JS_REPO/tests/fixtures/parity/emit.mjs" > "$tmp/js.json" 2>"$tmp/js.err"

if diff -u "$tmp/py.json" "$tmp/js.json" > "$tmp/resolution.diff"; then
  ok "py y js resuelven idéntico"
else
  bad "py y js difieren:"; cat "$tmp/resolution.diff"
fi

for runtime in py js; do
  if diff -u "$PY_REPO/tests/fixtures/parity/expected.json" "$tmp/$runtime.json" >/dev/null; then
    ok "$runtime coincide con expected.json"
  else
    bad "$runtime no coincide con expected.json"
    diff -u "$PY_REPO/tests/fixtures/parity/expected.json" "$tmp/$runtime.json" || true
  fi
  # §1.7: stdout solo lleva el resultado.
  if [[ -s "$tmp/$runtime.err" ]]; then
    echo "  (nota: $runtime escribió diagnóstico en stderr, que es lo correcto)"
  fi
done

# ---------------------------------------------------------------------------
step "2/5 Superficie de la CLI"

py_cli() { PYTHONPATH="$PY_REPO/src" "$PYTHON_BIN" -m env_manager.cli.main "$@"; }
js_cli() { node "$JS_REPO/dist/main.js" "$@"; }

# Se comparan los nombres de acción y de flag, no el texto de ayuda: cada
# runtime lo formatea distinto (argparse arma una ayuda por subcomando; el
# dispatcher de JS imprime una sola). El contrato es que existan los mismos
# flags, así que se junta la ayuda global con la de cada acción.
: > "$tmp/py-help.txt"
: > "$tmp/js-help.txt"
for action in "" encrypt decrypt secrets; do
  # shellcheck disable=SC2086
  py_cli $action --help >> "$tmp/py-help.txt" 2>&1 || true
  # shellcheck disable=SC2086
  js_cli $action --help >> "$tmp/js-help.txt" 2>&1 || true
done
py_cli secrets set --help >> "$tmp/py-help.txt" 2>&1 || true
py_cli secrets list --help >> "$tmp/py-help.txt" 2>&1 || true

extract_tokens() {
  grep -oE '(^|[[:space:]])(--[a-z-]+|encrypt|decrypt|secrets)' "$1" \
    | tr -d ' ' | sort -u
}
extract_tokens "$tmp/py-help.txt" > "$tmp/py-tokens.txt"
extract_tokens "$tmp/js-help.txt" > "$tmp/js-tokens.txt"

if diff -u "$tmp/py-tokens.txt" "$tmp/js-tokens.txt" > "$tmp/tokens.diff"; then
  ok "mismas acciones y flags"
else
  bad "la superficie de la CLI difiere:"; cat "$tmp/tokens.diff"
fi

# ---------------------------------------------------------------------------
step "3/5 Exit codes por categoría"

run_case() {
  local label="$1"; shift
  local py_code=0 js_code=0
  py_cli "$@" >/dev/null 2>&1 || py_code=$?
  js_cli "$@" >/dev/null 2>&1 || js_code=$?
  if [[ "$py_code" == "$js_code" ]]; then
    ok "$label -> $py_code (ambos)"
  else
    bad "$label -> py=$py_code js=$js_code"
  fi
}

run_case "sin acción"
run_case "acción desconocida" bogus
run_case "--help" --help
run_case "--version" --version
run_case "encrypt sin archivo" encrypt
run_case "--format inválido" encrypt algo --format bogus
run_case "decrypt archivo inexistente" decrypt /tmp/env-manager-parity-missing.env
run_case "secrets sin sub-acción" secrets
run_case "secrets list sin --project" secrets list app-config
run_case "secrets set sin --project" secrets set app-config --key K

# ---------------------------------------------------------------------------
step "4/5 PARITY.md"

if diff -u "$PY_REPO/PARITY.md" "$JS_REPO/PARITY.md" >/dev/null; then
  ok "copias idénticas en los dos repos"
else
  bad "PARITY.md difiere entre repos"
  diff -u "$PY_REPO/PARITY.md" "$JS_REPO/PARITY.md" || true
fi

if grep -q '| sin fase |' "$PY_REPO/PARITY.md"; then
  bad "quedan filas en estado 'sin fase'"
  grep -n '| sin fase |' "$PY_REPO/PARITY.md" || true
else
  ok "ninguna fila en estado 'sin fase'"
fi

# Toda brecha declarada necesita dueño y fecha (§1.3.1).
if "$PYTHON_BIN" - "$PY_REPO/PARITY.md" <<'PYEOF'
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
section = text.split("## Brechas declaradas")[1].split("\n## ")[0]
rows = [
    line for line in section.splitlines()
    if line.startswith("|") and not line.startswith("|---") and "qué falta" not in line
]
bad_rows = []
for row in rows:
    cells = [c.strip() for c in row.strip("|").split("|")]
    if len(cells) < 3 or not cells[1] or not cells[2]:
        bad_rows.append(row)
    elif not re.search(r"\d{4}-\d{2}-\d{2}", cells[2]) and "sin fecha" not in cells[2]:
        bad_rows.append(row)
if bad_rows:
    print("\n".join(bad_rows))
    sys.exit(1)
PYEOF
then
  ok "toda brecha declarada tiene dueño y fecha"
else
  bad "hay brechas declaradas sin dueño o sin fecha"
fi

# ---------------------------------------------------------------------------
step "5/5 Suites"

# El extra `encrypted` no instala en todos los intérpretes (coincurve no
# publica wheel para 3.14). Es una brecha DECLARADA en PARITY.md: si la fila no
# está, no se permite el salteo y el gate falla como corresponde.
pytest_args=(-q)
if ! "$PYTHON_BIN" -c "import ecies" >/dev/null 2>&1; then
  if grep -q "coincurve" "$PY_REPO/PARITY.md"; then
    echo "  WARN eciespy no está instalado: se saltan los tests de dotenv cifrado."
    echo "       Brecha declarada en PARITY.md (extra 'encrypted' con Python 3.14)."
    pytest_args+=(--ignore=tests/test_cli_encrypt.py --ignore=tests/test_encrypted_dotenv.py)
  else
    bad "eciespy no está instalado y la brecha no está declarada en PARITY.md"
  fi
fi

if ( cd "$PY_REPO" && "$PYTHON_BIN" -m pytest "${pytest_args[@]}" > "$tmp/pytest.log" 2>&1 ); then
  ok "pytest"
else
  bad "pytest"; tail -20 "$tmp/pytest.log"
fi

if ( cd "$JS_REPO" && npx vitest run > "$tmp/vitest.log" 2>&1 ); then
  ok "vitest"
else
  bad "vitest"; tail -20 "$tmp/vitest.log"
fi

if ( cd "$JS_REPO" && npx tsc --noEmit > "$tmp/tsc.log" 2>&1 ); then
  ok "tsc --noEmit"
else
  bad "tsc --noEmit"; tail -20 "$tmp/tsc.log"
fi

# ---------------------------------------------------------------------------
printf '\n===========================================\n'
if [[ "$failures" -eq 0 ]]; then
  echo "GATE VERDE — se puede abrir PR / publicar."
  exit 0
fi
echo "GATE ROJO — $failures verificación(es) fallida(s). No hay PR ni publicación."
exit 1
