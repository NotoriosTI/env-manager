"""Alias deprecado de ``env-manager decrypt``.

Existe solo por paridad con el runtime JS, que ya publicaba el binario
``env-manager-decrypt``. Se elimina en la versión siguiente.
"""

from __future__ import annotations

import sys

from env_manager.cli.main import main as dispatch


def main() -> None:
    print(
        "Warning: 'env-manager-decrypt' is deprecated and will be removed in the "
        "next release. Use 'env-manager decrypt' instead.",
        file=sys.stderr,
    )
    dispatch(["decrypt", *sys.argv[1:]])
