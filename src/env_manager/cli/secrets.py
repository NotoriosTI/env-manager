"""Rotación del secreto JSON consolidado de una app (blueprint §1.1).

Regla del blueprint: cada app tiene **un** secreto JSON consolidado en Google
Secret Manager y el guardado de una actualización no puede dejar versiones
viejas activas — se paga por versión habilitada. Este módulo es la única pieza
que escribe en GSM, y lo hace en un orden que nunca deja la app sin secreto
legible:

1. leer el JSON de la versión ``latest``;
2. mezclar la clave nueva;
3. si el contenido no cambió, no se crea versión (idempotente);
4. agregar la versión nueva;
5. **verificar** que la versión nueva se lee y trae la clave;
6. recién entonces destruir las demás versiones habilitadas.

Si el paso 6 falla, el comando lo dice con el número de versión que quedó
colgando y sale con código de error. Nada de ``|| true``.

El valor nunca entra por argumento: se lee de stdin. Un valor en ``argv`` queda
en ``ps`` y en el historial del shell.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable, Optional

from env_manager.utils import logger


class SecretsError(RuntimeError):
    """Fallo de operación contra Secret Manager."""


class SecretDestroyError(SecretsError):
    """La versión nueva quedó bien, pero no se pudo destruir una vieja."""


def _client() -> Any:
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()


def _secret_path(project_id: str, secret_name: str) -> str:
    return f"projects/{project_id}/secrets/{secret_name}"


def _read_latest(client: Any, project_id: str, secret_name: str) -> dict[str, Any]:
    """Read the consolidated JSON from ``latest``.

    Un secreto que no existe es un error: crear secretos es una acción de
    infraestructura, y el blueprint pide que los secretos nuevos nazcan vacíos
    de la mano de una persona.
    """

    from google.api_core import exceptions as gcp_exceptions

    name = f"{_secret_path(project_id, secret_name)}/versions/latest"
    try:
        response = client.access_secret_version(name=name)
    except gcp_exceptions.NotFound as exc:
        raise SecretsError(
            f"Secret '{secret_name}' does not exist in project '{project_id}'. "
            "Create it empty first; env-manager does not create secrets."
        ) from exc
    except gcp_exceptions.PermissionDenied as exc:
        raise SecretsError(
            f"Permission denied reading '{secret_name}' in project '{project_id}'. "
            "Retrying will not help; check IAM."
        ) from exc

    raw = response.payload.data.decode("utf-8").strip()
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise SecretsError(
            f"Secret '{secret_name}' does not contain valid JSON. Refusing to "
            "overwrite it: fix the payload by hand first."
        ) from exc

    if not isinstance(data, dict):
        raise SecretsError(
            f"Secret '{secret_name}' must contain a JSON object, got "
            f"{type(data).__name__}. Refusing to overwrite it."
        )
    return data


def _enabled_versions(client: Any, project_id: str, secret_name: str) -> list[str]:
    """Return the names of every ENABLED version, newest first."""

    parent = _secret_path(project_id, secret_name)
    names: list[str] = []
    for version in client.list_secret_versions(parent=parent):
        state = getattr(version, "state", None)
        state_name = getattr(state, "name", str(state))
        if state_name == "ENABLED":
            names.append(version.name)
    return names


def list_keys(project_id: str, secret_name: str, *, client: Any = None) -> list[str]:
    """Return the key names in the consolidated secret. Never the values."""

    client = client or _client()
    return sorted(_read_latest(client, project_id, secret_name))


def set_key(
    project_id: str,
    secret_name: str,
    key: str,
    value: str,
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Set ``key`` in the consolidated secret, destroying the previous version.

    Devuelve un resumen con la versión creada y las destruidas. Cuando el valor
    ya estaba, no crea versión y lo informa.
    """

    if not key:
        raise SecretsError("A key name is required.")

    client = client or _client()
    parent = _secret_path(project_id, secret_name)

    current = _read_latest(client, project_id, secret_name)

    if current.get(key) == value:
        # §1.5: no se paga una versión nueva por escribir lo mismo.
        return {
            "secret": secret_name,
            "key": key,
            "created_version": None,
            "destroyed_versions": [],
            "unchanged": True,
        }

    previous_versions = _enabled_versions(client, project_id, secret_name)

    updated = dict(current)
    updated[key] = value
    payload = json.dumps(updated, sort_keys=True, indent=2).encode("utf-8")

    added = client.add_secret_version(
        parent=parent, payload={"data": payload}
    )
    new_version = added.name

    # Verificación antes de destruir nada: si la versión nueva no se puede leer,
    # destruir la vieja dejaría la app sin secreto.
    verify = client.access_secret_version(name=new_version)
    verify_payload = json.loads(verify.payload.data.decode("utf-8"))
    if verify_payload.get(key) != value:
        raise SecretsError(
            f"Wrote version {new_version} but reading it back did not return the "
            "expected value. Nothing was destroyed; inspect the secret by hand."
        )

    destroyed: list[str] = []
    for version_name in previous_versions:
        if version_name == new_version:
            continue
        try:
            client.destroy_secret_version(name=version_name)
        except Exception as exc:  # noqa: BLE001 - se reporta con nombre y todo
            raise SecretDestroyError(
                f"New version {new_version} is live, but destroying {version_name} "
                f"failed: {exc}. That version is still billable — destroy it by hand."
            ) from exc
        destroyed.append(version_name)

    logger.info(
        f"Set '{key}' in '{secret_name}': created {new_version}, "
        f"destroyed {len(destroyed)} previous version(s)."
    )

    return {
        "secret": secret_name,
        "key": key,
        "created_version": new_version,
        "destroyed_versions": destroyed,
        "unchanged": False,
    }


def read_value_from_stdin(stream: Optional[Iterable[str]] = None) -> str:
    """Read the secret value from stdin.

    El valor nunca viaja por ``argv``: quedaría en ``ps`` y en el historial.
    """

    source = stream if stream is not None else sys.stdin
    value = "".join(source)
    if value.endswith("\n"):
        value = value[:-1]
    if not value:
        raise SecretsError("No value provided on stdin.")
    return value
