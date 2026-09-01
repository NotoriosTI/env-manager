"""Loader implementation backed by Google Secret Manager."""

from __future__ import annotations

import json
import os
from typing import Optional

from google.api_core import exceptions as gcp_exceptions
from google.api_core import retry as gcp_retry
from google.cloud import secretmanager

from env_manager.base import SecretLoader

from env_manager.utils import logger

#: Timeout por llamada a GSM, en segundos. Blueprint §1.5.3: todo proceso remoto
#: tiene timeout. Nunca se deja el default de la librería cliente.
DEFAULT_GCP_TIMEOUT = 10.0

#: Tope de reintentos. §1.5.3: todo reintento tiene tope.
MAX_RETRY_ATTEMPTS = 3

#: §1.5.4: solo lo transitorio se reintenta. Un `PermissionDenied` o un
#: `InvalidArgument` es determinista: reintentarlo quema tiempo para morir igual.
TRANSIENT_ERRORS = (
    gcp_exceptions.ServiceUnavailable,
    gcp_exceptions.DeadlineExceeded,
    gcp_exceptions.TooManyRequests,
    gcp_exceptions.InternalServerError,
    gcp_exceptions.Aborted,
)

#: Errores deterministas: se reportan de inmediato, sin reintento.
DETERMINISTIC_ERRORS = (
    gcp_exceptions.PermissionDenied,
    gcp_exceptions.Unauthenticated,
    gcp_exceptions.InvalidArgument,
    gcp_exceptions.FailedPrecondition,
)


def _resolve_timeout(provided: Optional[float]) -> float:
    """Resolve the per-call GSM timeout: argumento > env var > default."""

    if provided is not None:
        return float(provided)

    raw = os.getenv("ENV_MANAGER_GCP_TIMEOUT")
    if raw:
        try:
            value = float(raw)
        except ValueError:
            logger.warning(
                f"ENV_MANAGER_GCP_TIMEOUT='{raw}' is not a number; "
                f"falling back to {DEFAULT_GCP_TIMEOUT}s."
            )
            return DEFAULT_GCP_TIMEOUT
        if value <= 0:
            logger.warning(
                f"ENV_MANAGER_GCP_TIMEOUT='{raw}' must be positive; "
                f"falling back to {DEFAULT_GCP_TIMEOUT}s."
            )
            return DEFAULT_GCP_TIMEOUT
        return value

    return DEFAULT_GCP_TIMEOUT


def _is_transient(exc: Exception) -> bool:
    """Predicate for the retry policy: only transient failures are retried."""

    return isinstance(exc, TRANSIENT_ERRORS)


class GCPSecretLoader(SecretLoader):
    """Load secrets from GCP Secret Manager with simple caching.

    When ``consolidated_secret`` is set, that single secret is fetched once
    and must contain a JSON object; its entries pre-populate the cache so
    resolving each key costs zero extra API calls. Keys absent from the
    consolidated payload fall back to individual secret lookups.
    """

    def __init__(
        self,
        project_id: str,
        consolidated_secret: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if not project_id:
            raise ValueError(
                "GCP project ID is required when using the GCP secret loader."
            )
        self._project_id = project_id
        self._client = secretmanager.SecretManagerServiceClient()
        self._cache: dict[str, Optional[str]] = {}
        self._consolidated_secret = consolidated_secret
        self._consolidated_loaded = False
        self._timeout = _resolve_timeout(timeout)
        self._retry = gcp_retry.Retry(
            predicate=_is_transient,
            initial=0.5,
            maximum=4.0,
            multiplier=2.0,
            timeout=self._timeout * MAX_RETRY_ATTEMPTS,
        )

    @property
    def timeout(self) -> float:
        """Per-call timeout applied to every Secret Manager request."""

        return self._timeout

    def _secret_resource(self, secret_name: str) -> str:
        return f"projects/{self._project_id}/secrets/{secret_name}/versions/latest"

    def _access(self, key: str) -> Optional[str]:
        """Fetch one secret payload, or None when the secret does not exist."""
        name = self._secret_resource(key)

        try:
            response = self._client.access_secret_version(
                name=name, timeout=self._timeout, retry=self._retry
            )
        except gcp_exceptions.NotFound:
            logger.warning(
                f"Secret '{key}' not found in GCP project '{self._project_id}'."
            )
            return None
        except DETERMINISTIC_ERRORS as exc:
            # §1.5.4: determinista. No se reintenta y se dice por qué.
            raise RuntimeError(
                f"Deterministic failure accessing secret '{key}' in GCP project "
                f"'{self._project_id}': {type(exc).__name__}: {exc}. "
                "Retrying will not help; check IAM permissions, credentials "
                "and the secret name."
            ) from exc
        except gcp_exceptions.RetryError as exc:
            raise RuntimeError(
                f"Retries exhausted after {self._timeout * MAX_RETRY_ATTEMPTS:.1f}s "
                f"accessing secret '{key}' in GCP project '{self._project_id}': {exc}"
            ) from exc
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(
                "Failed to access secret "
                f"'{key}' in GCP project '{self._project_id}': {exc}"
            ) from exc

        return response.payload.data.decode("utf-8")

    def _preload_consolidated(self) -> None:
        if self._consolidated_loaded or not self._consolidated_secret:
            return
        self._consolidated_loaded = True

        payload = self._access(self._consolidated_secret)
        if payload is None:
            logger.warning(
                f"Consolidated secret '{self._consolidated_secret}' not found; "
                "falling back to individual secret lookups."
            )
            return
        try:
            data = json.loads(payload)
        except ValueError:
            logger.warning(
                f"Consolidated secret '{self._consolidated_secret}' is not valid "
                "JSON; falling back to individual secret lookups."
            )
            return
        if not isinstance(data, dict):
            logger.warning(
                f"Consolidated secret '{self._consolidated_secret}' must be a "
                "JSON object; falling back to individual secret lookups."
            )
            return

        for key, value in data.items():
            if key not in self._cache:
                self._cache[key] = (
                    value if isinstance(value, str) else json.dumps(value)
                )
        logger.info(
            f"Preloaded {len(data)} values from consolidated secret "
            f"'{self._consolidated_secret}'."
        )

    def get(self, key: str) -> Optional[str]:
        self._preload_consolidated()

        if key in self._cache:
            return self._cache[key]

        payload = self._access(key)
        self._cache[key] = payload
        return payload

    def get_many(self, keys: list[str]) -> dict[str, Optional[str]]:
        return {key: self.get(key) for key in keys}

    @property
    def project_id(self) -> str:
        """Return the configured GCP project identifier."""

        return self._project_id
