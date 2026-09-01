"""Exit codes estables de la CLI (blueprint §1.7).

Cada categoría de error tiene un código propio y el mismo número en el runtime
JS. Un consumidor puede ramificar por código sin parsear texto.
"""

from __future__ import annotations

#: Todo salió bien.
OK = 0

#: Error de uso: falta un argumento, la acción no existe, la combinación de
#: flags no es válida. Se acompaña siempre del texto de ayuda.
USAGE = 1

#: Error de operación: el archivo no existe, ya estaba cifrado, el .env.keys ya
#: existe, el descifrado falló. El comando es correcto; el estado del mundo no.
OPERATION = 2

#: Falta una dependencia opcional (por ejemplo el extra `encrypted`).
DEPENDENCY = 3

#: Falla contra un servicio remoto (Secret Manager). Ver §1.5.4 para la
#: distinción entre transitorio y determinista.
REMOTE = 4
