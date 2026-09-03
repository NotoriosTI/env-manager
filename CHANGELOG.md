# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).
Este proyecto sigue versionado semántico.

## [0.4.1] — 2026-09-03

### Añadido

- `secrets set --allow-empty` permite almacenar intencionalmente una cadena
  vacía; sin el flag, stdin vacío sigue siendo un error.
- `fallback_to_individual` en YAML y API permite hacer autoritativo el secreto
  consolidado. Conserva `true` como valor predeterminado compatible.
- Un resumen agregado por carga informa cuántas claves vinieron del JSON,
  requirieron acceso individual o quedaron ausentes, sin exponer nombres ni
  valores.

### Corregido

- La rotación destruye versiones anteriores `ENABLED` y `DISABLED`, ya que
  ambas son facturables, e inicializa desde `{}` un recurso sin versiones.
- El warning por `GCP_PROJECT_ID` sólo aparece cuando el origen global efectivo
  es GCP.
- Los ejemplos y el smoke test usan `APP_ENV`, que es el selector soportado.

### Notas

- Las escrituras concurrentes al mismo secreto no están soportadas y deben
  serializarse externamente.
- `SECRET_ORIGIN`, `GCP_PROJECT_ID` y `CONSOLIDATED_SECRET` definidos en el
  entorno o `.env` prevalecen sobre el YAML.

## [0.4.0] — 2026-09-01

Primera versión alineada con el blueprint §1 de la base de conocimiento
(`conocimiento.notorios.cl/#/p/4b2b7217953e`). Absorbe la `0.3.0`, que quedó
commiteada pero **nunca se publicó en PyPI**: quien venga de `0.2.3` recibe
también el soporte de secreto consolidado que traía aquella.

### Añadido

- **CLI unificada `env-manager <acción>`** (§1.7). Un solo binario con el nombre
  de la aplicación y las acciones como subcomandos:

  ```
  env-manager encrypt <file> [--env NAME] [--force] [-o OUT] [--format text|json]
  env-manager decrypt <file> [--env NAME] [--key HEX] [-o OUT] [--format text|json]
  env-manager secrets list <secret> --project PROJECT
  env-manager secrets set  <secret> --key KEY --project PROJECT   # valor por stdin
  ```

- **`env-manager decrypt`**: antes solo existía en el runtime JS.
- **`env-manager secrets set`** (§1.1): escribe una clave en el secreto JSON
  consolidado de la app y **destruye la versión anterior**, que se sigue
  facturando mientras esté habilitada. Lee el JSON actual, mezcla la clave,
  agrega la versión nueva, la lee de vuelta para verificarla y recién entonces
  destruye las viejas. Escribir el mismo valor no crea versión. El valor entra
  por stdin, nunca por `argv`.
- **`env-manager secrets list`**: nombres de clave, nunca valores.
- **`--format json`** en toda acción automatizable.
- **Exit codes estables por categoría**: `0` éxito, `1` uso, `2` operación,
  `3` dependencia opcional faltante, `4` fallo remoto.
- **Timeout explícito en cada llamada a Secret Manager** (§1.5.3): 10 s por
  defecto, configurable por constructor o por `ENV_MANAGER_GCP_TIMEOUT`, con
  tope de 3 intentos.
- **Taxonomía de errores transitorio vs determinista** (§1.5.4): un
  `PermissionDenied` falla al primer intento diciendo que reintentar no ayuda;
  un `ServiceUnavailable` se reintenta dentro del tope.
- `_reset_singleton()` y exports de `coerce_type`, `load_yaml`, `mask_secret`,
  `parse_environments`, `DotEnvLoader`, `GCPSecretLoader` desde la raíz del
  paquete, por paridad con el runtime JS.
- `PARITY.md`: contrato de paridad con env-manager-js, y
  `scripts/parity-check.sh`, el gate que lo verifica.
- Test de integración real contra Secret Manager, saltado por defecto y
  limitado a un proyecto descartable explícito
  (`RUN_REAL_GCP_TESTS=1 ENV_MANAGER_ITEST_PROJECT=<proyecto>`).
- CI: matriz 3.12 / 3.13 con el extra `encrypted` y 3.14 sin él.

### Cambiado

- `requires-python` pasa de `>=3.13` a **`>=3.12`**. La suite completa corre
  verde en 3.12 y en 3.13; el piso anterior excluía consumidores sin motivo.
- Los errores de la CLI ahora salen con su exit code por categoría en vez de
  `1` para todo. **Si automatizabas contra el código `1`, revísalo.**

### Obsoleto

- `env-manager-encrypt` y `env-manager-decrypt` siguen funcionando **una
  versión**: avisan por stderr y delegan en el dispatcher. Se eliminan en la
  siguiente.

### Corregido

- Los tests apuntaban a un fixture cifrado borrado en `a8cbf7c` y traían la
  llave privada de ese fixture escrita en el cuerpo del test. Ahora generan una
  llave efímera por sesión; no queda material de llave en el repositorio.
- Mensajes de error que citaban el nombre viejo del paquete.

### Notas

- El extra `encrypted` **no instala en Python 3.14**: `coincurve` no publica
  wheel para cp314 en macOS ni Linux. Aplica también en runtime, no solo al
  cifrar. El core funciona en 3.14; solo el extra está topado.
