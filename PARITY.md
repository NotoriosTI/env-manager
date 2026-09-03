# PARITY.md — contrato de paridad env-manager (py) ↔ env-manager-js

Este archivo es **idéntico byte a byte** en `NotoriosTI/env-manager` y
`NotoriosTI/env-manager-js`. Si lo editas en uno, lo copias al otro en el mismo
PR. Un diff entre las dos copias es un fallo del gate.

Referencia normativa: conocimiento.notorios.cl `4b2b7217953e` §1.
Plan de trabajo: `.planning/PLAN-blueprint-compliance.md`.
Estado verificado contra: env-manager 0.4.1 · env-manager-js 0.3.1 (2026-09-03).

## Regla de oro

Python es la implementación de referencia. Cuando las dos difieren y no hay una
fila que declare la diferencia como intencional, **el comportamiento correcto es
el de Python** y JS es el que se corrige.

Ninguna release sale, ni de PyPI ni de npm, sin `scripts/parity-check.sh` en
verde y su reporte pegado en el PR.

## Fixture canónico

`tests/fixtures/parity/` — mismos archivos en ambos repos:

| archivo | qué es |
|---|---|
| `config.yaml` | configuración canónica: alias de origin, cuatro tipos, default presente y ausente, coerción bool→str, required/optional |
| `parity.env` | valores de entrada |
| `expected.json` | salida esperada, ordenada por clave, indentación 2 |
| `emit.py` / `emit.mjs` | emisores; solo usan API pública común (`ConfigManager`, `load`, `get`) |
| `pyproject.toml` / `package.json` | anclas de descubrimiento de raíz (ver D9). No son paquetes |

Contrato del emisor: **stdout contiene solo el JSON**, ordenado por clave, con
indentación de 2. Todo log va a stderr. Exit code 0 en éxito.

El fixture no toca GSM a propósito: el gate tiene que correr sin credenciales.

### Integración contra GSM real

Además del fixture offline, cada repo trae un test de integración espejo que
crea un secreto JSON consolidado de mentira en Secret Manager, comprueba que se
lee y que sus valores se comportan como cualquier secreto individual, y lo borra
en el teardown pase lo que pase:

- `tests/test_consolidated_secret_gsm_integration.py` (14 casos)
- `tests/consolidated-secret-gsm-integration.test.ts` (13 casos)

Se saltan por defecto. Para correrlos:

```bash
RUN_REAL_GCP_TESTS=1 ENV_MANAGER_ITEST_PROJECT=<proyecto> pytest -m integration
RUN_REAL_GCP_TESTS=1 ENV_MANAGER_ITEST_PROJECT=<proyecto> npx vitest run tests/consolidated-secret-gsm-integration.test.ts
```

Los secretos que crean llevan prefijo `env-manager-itest-`. Si alguno queda
huérfano, sus versiones `ENABLED` y `DISABLED` siguen siendo facturables
(§1.1): bórralo.

El gate no los corre — necesitan credenciales y crean recursos.

## Contrato de la CLI (§1.7)

Un solo binario por runtime, con el nombre de la aplicación:

```
env-manager encrypt <file> [--env N] [--force] [-o OUT] [--format text|json]
env-manager decrypt <file> [--env N] [--key HEX] [-o OUT] [--format text|json]
env-manager secrets list <secret> --project P [--format text|json]
env-manager secrets set  <secret> --key K --project P [--allow-empty] [--format text|json]   # valor por stdin
env-manager --version | --help
```

`env-manager-encrypt` y `env-manager-decrypt` siguen existiendo **una versión**
como alias deprecados: avisan por stderr y delegan en el dispatcher, con los
mismos exit codes. Se eliminan en la release siguiente.

Exit codes, iguales en los dos runtimes
(`env_manager/cli/exit_codes.py` ↔ `src/cli/exitCodes.ts`):

| código | significado |
|---|---|
| 0 | éxito |
| 1 | error de uso: falta un argumento, la acción no existe, flags inválidos |
| 2 | error de operación: el archivo no existe, ya estaba cifrado, el descifrado falló |
| 3 | falta una dependencia opcional (extra `encrypted`) |
| 4 | falla contra un servicio remoto (Secret Manager) |

Los resultados van a stdout, el diagnóstico a stderr, siempre.

## Matriz

Leyenda: **paridad** · **declarada** (brecha intencional, con dueño y fecha
abajo).

### API pública

| id | tema | Python | JS | estado |
|---|---|---|---|---|
| — | `ConfigManager`, `load`, `get` | sí | sí | paridad |
| — | `load` sync vs async | sync | `Promise` | paridad (diferencia de lenguaje) |
| D1 | re-inicializar el singleton | reemplaza la instancia y advierte | reemplaza la instancia y advierte (`manager.ts:1111`) | paridad |
| D2 | `get_config` / `getConfig` | `(key, default=None)`; falla si no hay singleton | `(name?, defaultValue=null)`; falla si no hay singleton; sin nombre devuelve el manager | paridad (el retorno del manager es extensión de JS) |
| D3 | reinicio del singleton para tests | `_reset_singleton()` | `_resetSingleton()` | paridad |
| D4 | métodos de instancia | `get`, `require`, `values`, `active_environment` | `get`, `require`, `values`, `activeEnvironment`, `load` | paridad |
| D5 | `NotImplementedError` | no existe | `errors.ts:6` | declarada (deriva de H6) |
| D6 | `ConfigValidationIssue`, `DecryptionIssue` | clases | tipos TS | paridad (diferencia de lenguaje) |
| D7 | exports auxiliares | `coerce_type`, `load_yaml`, `mask_secret`, `parse_environments`, `DotEnvLoader`, `GCPSecretLoader`, `create_loader`, `SecretLoader`, `EnvironmentConfig` | mismos, en camelCase | paridad |
| D8 | opciones del constructor | `secret_origin`, `gcp_project_id`, `strict`, `auto_load`, `dotenv_path`, `debug`, `consolidated_secret`, `fallback_to_individual` | mismas en camelCase, sin `autoLoad` | `autoLoad` declarada (el constructor de JS no puede esperar una promesa) |

### Configuración YAML

| tema | Python | JS | estado |
|---|---|---|---|
| `environments.<n>.origin` + alias (`dotenv`, `env-file`, `.env`, `gcp-secretmanager`, `gcp-secret-manager`, `secretmanager`) | sí | sí, mismo set | paridad |
| `dotenv_path`, `gcp_project_id`, `default` | sí | sí | paridad |
| `encrypted_dotenv.enabled` + `private_key.{source,secret_origin,dotenv_path,gcp_project_id}` | sí | parsea, pero falla en runtime | ver H6 |
| `consolidated_secret` (por entorno, por `CONSOLIDATED_SECRET` o por opción explícita) | sí | sí | paridad |
| `fallback_to_individual` (por entorno o por opción explícita; predeterminado `true`; `false` requiere consolidado) | sí | sí | paridad |
| `variables.<n>.{source,type,default,origin,secret_origin,dotenv_path,gcp_project_id,environment,required}` | sí | sí (normaliza snake_case → camelCase) | paridad |
| `validation.{strict,required,optional}` | sí | sí | paridad |
| tipos `str`, `int`, `float`, `bool` y coerción bool→str | sí | sí | paridad (verificado por el fixture) |

### Comportamiento

| id | tema | Python | JS | estado |
|---|---|---|---|---|
| D9 | descubrimiento de raíz de proyecto | marcador del lenguaje, techo en `.git`, fallback al directorio del config | igual, con `package.json` como marcador | paridad |
| D10 | separación de streams | `logger` sin handler; stdout limpio | `logger` a stderr; stdout limpio | paridad |
| H4 | timeout por llamada a GSM | 10 s, override por ctor y `ENV_MANAGER_GCP_TIMEOUT` | igual | paridad |
| H4b | taxonomía transitorio vs determinista | transitorios reintentados con tope 3; deterministas fallan al primer intento con "Retrying will not help" | igual, por código gRPC | paridad |
| H5 | errores tragados | — | ningún `catch {}` vacío: se avisa antes de degradar | paridad |
| H6 | dotenv cifrado en runtime | soportado | lanza `NotImplementedError` | declarada |
| D11 | clave con la que se exporta a `os.environ` / `process.env` | el **nombre** de la variable (`manager.py:503`) | el **nombre** de la variable, más el `source` como alias deprecado por una versión | paridad (con alias transitorio, ver abajo) |
| D12 | precarga del consolidado con `getMany` concurrente | N/A (síncrono) | una sola promesa compartida; antes cada clave caía a búsqueda individual | paridad |
| D13 | consolidado autoritativo | con fallback desactivado no consulta secretos individuales y un consolidado ausente o inválido falla | igual | paridad |
| D14 | resumen agregado de carga | conteos sin nombres ni valores; `INFO` sin accesos individuales ni ausencias, `WARNING` en caso contrario | igual | paridad |

### CLI (§1.7)

| id | tema | Python | JS | estado |
|---|---|---|---|---|
| H3 | binario `env-manager <acción>` | sí | sí | paridad |
| H2 | `decrypt` | sí (`--env`, `--key`, `-o/--output`) | sí (mismos flags) | paridad |
| — | `encrypt` | sí (`--env`, `--force`, `-o/--output`) | sí (mismos flags) | paridad |
| — | `--format json` | sí | sí | paridad |
| — | exit codes por categoría | sí | sí | paridad (verificado por el gate) |
| — | alias deprecados con warning a stderr | sí | sí | paridad |
| H8 | `secrets set` con destrucción de versiones anteriores facturables | sí | sí | paridad |
| — | `secrets list` (solo nombres, nunca valores) | sí | sí | paridad |
| — | `auth login/status/logout` | no aplica | no aplica | exención, ver abajo |

## Rotación de secretos (§1.1)

`env-manager secrets set` es la única pieza que escribe en Secret Manager. El
orden no es negociable y está probado en los dos runtimes:

1. tomar una instantánea de las versiones existentes;
2. leer el JSON de `latest`, o usar `{}` si el recurso existe sin versiones;
3. mezclar la clave (no reemplaza el payload);
4. si el valor ya estaba, **no** crea versión;
5. agregar la versión nueva;
6. leerla de vuelta y verificar que trae la clave;
7. recién ahí destruir las versiones anteriores `ENABLED` y `DISABLED`.

Reglas que el gate y los tests protegen:

- El valor entra por **stdin**, nunca por `argv` — en `argv` queda en `ps` y en
  el historial del shell.
- Stdin vacío es un error salvo con `--allow-empty`, que almacena `""`.
- `secrets list` devuelve nombres de clave, nunca valores.
- Un recurso existente sin versiones parte desde `{}`; un recurso inexistente
  sigue siendo un error y no se crea implícitamente.
- Un payload que no es JSON, o que no es un objeto, no se sobrescribe.
- Si la destrucción falla, el comando sale con código 4 nombrando la versión
  que quedó facturándose. Nada de `|| true`.
- Las escrituras concurrentes al mismo secreto no están soportadas: los
  escritores deben serializarse externamente.

## D11: con qué clave se exporta al entorno

El nombre de la variable es el contrato con el mundo exterior; el `source` es
solo dónde está guardado el valor. Un config que declara `PGHOST` con
`source: JUAN_DB_HOST` quiere que libpq encuentre `PGHOST`.

Python siempre exportó con el nombre. JS exportaba con el `source`, así que
`PGHOST` nunca aparecía y la librería externa no veía nada. Medido sobre los
consumidores reales, el 77% de las variables declaradas (1414 de 1843) tienen
`source` distinto del nombre, así que no era un caso borde.

Desde js 0.3.0 los dos exportan con el nombre. Por una versión, JS **además**
exporta bajo el `source` cuando difiere, con un warning por stderr, para no
romper a quien dependa de la conducta vieja. Ese alias se elimina en la release
siguiente y está anotado como brecha declarada.

## Exenciones

**§1.7 `auth`.** El blueprint exige `auth login/status/logout` con Device
Authorization Flow a toda aplicación que exponga control por terminal.
env-manager es una librería sin backend propio y sin sesión: no hay servidor
contra el cual autenticar ni token que rotar. La autenticación a GCP la resuelve
ADC, fuera del alcance de la librería. El resto de §1.7 (nombre del binario,
estructura `nombre-app <acción>`, `--format json`, stdout/stderr, exit codes
estables) sí aplica y está implementado.

## Brechas declaradas (§1.3.1: qué falta · quién · fecha)

| qué falta | quién lo responde | fecha |
|---|---|---|
| Carga de dotenv cifrado en runtime en JS (H6, D5) | bastianibanez | 2026-11-30 |
| `autoLoad` en el constructor de JS (D8): el constructor no puede esperar la promesa de `load()`; hoy se resuelve con `await initConfig()` | bastianibanez | 2026-11-30 |
| Renombrar los repos según §1.0 (`notorios-apps-…`); rompe URLs de PyPI, npm, GitHub y referencias en repos consumidores | bastianibanez | sin fecha — declarado no prioritario |
| Quitar el alias transitorio de D11 en JS: dejar de exportar bajo el `source` cuando difiere del nombre. Sale en la release siguiente a la 0.3.0, y a más tardar en esta fecha | bastianibanez | 2026-10-31 |
| Extra `encrypted` no instalable con Python 3.14: `coincurve` no publica wheel para cp314 en macOS ni Linux. El core sí funciona en 3.14; solo el extra está topado. El venv del repo usa 3.13, donde la suite corre completa; `requires-python` es `>=3.12,<4.0` | bastianibanez | sin fecha — depende de upstream (coincurve) |

Una fila sin dueño **o** sin fecha hace fallar el gate. "Sin fecha" se acepta
solo en dos casos, ambos registrados en el plan: el renombrado de repos (decisión
explícita de no priorizarlo) y el techo del extra `encrypted` (depende de que
`coincurve` publique wheels para 3.14, que no está en nuestras manos).

## Gate

`scripts/parity-check.sh`, idéntico en ambos repos. Corre antes de cualquier PR
a `main` y antes de publicar. Los cinco pasos:

1. **Resolución.** `emit.py` y `emit.mjs` contra el fixture; su stdout debe ser
   idéntico entre sí e idéntico a `expected.json`.
2. **Superficie CLI.** Mismas acciones y mismos flags en el `--help` de ambos.
3. **Exit codes.** Diez invocaciones de error; py y js deben devolver el mismo
   código en cada una.
4. **Este archivo.** Copias idénticas en ambos repos; cero filas en estado
   *sin fase*; cero brechas declaradas sin dueño o sin fecha.
5. **Suites.** `pytest` verde · `vitest run` y `tsc --noEmit` verdes.

Corre igual desde cualquiera de los dos repos: ubica al hermano por
`ENV_MANAGER_PY` / `ENV_MANAGER_JS`, o por convención de directorio hermano.

En CI lo ejecuta el job `parity` de `.github/workflows/ci.yml`, presente en
ambos repos, que hace checkout de los dos y corre el mismo script. Los dos
repos son públicos, así que el cross-checkout no necesita token y los minutos
no se facturan (§1.6.1).

La matriz de tests de Python cubre 3.12 y 3.13 con el extra `encrypted`, y 3.14
sin el extra: así el techo de `coincurve` deja de ser una nota en el README y
pasa a ser algo que CI verifica (§1.5.7).

Salida: reporte pegado en el PR. Sin reporte, no hay merge.
