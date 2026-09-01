"""Emisor de paridad — runtime Python.

Resuelve el fixture canónico e imprime en stdout el JSON de valores, ordenado
por clave y con indentación de 2. Nada más va a stdout.

Solo usa API pública común a ambos runtimes (`ConfigManager`, `load`, `get`):
así el emisor no depende de métodos que hoy existen en un runtime y no en el
otro. Ver la fila D7 de PARITY.md.

Uso, desde la raíz del repo:
    python tests/fixtures/parity/emit.py
"""

import json
import os
import sys
from pathlib import Path

import yaml

FIXTURE_DIR = Path(__file__).resolve().parent
REPO_ROOT = FIXTURE_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "src"))
os.chdir(FIXTURE_DIR)

from env_manager import ConfigManager  # noqa: E402

with open("config.yaml", encoding="utf-8") as handle:
    names = sorted(yaml.safe_load(handle)["variables"])

manager = ConfigManager("config.yaml")
manager.load()
print(json.dumps({name: manager.get(name) for name in names}, sort_keys=True, indent=2))
