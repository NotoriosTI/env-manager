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
        *,
        fallback_to_individual: bool = True,
    ) -> None:
        if not project_id:
            raise ValueError(
                "GCP project ID is required when using the GCP secret loader."
            )
        if not isinstance(fallback_to_individual, bool):
            raise ValueError("fallback_to_individual must be a boolean.")
        if not fallback_to_individual and not consolidated_secret:
            raise ValueError(
                "fallback_to_individual=False requires a consolidated_secret."
            )
        self._project_id = project_id
        self._client = secretmanager.SecretManagerServiceClient()
        self._cache: dict[str, Optional[str]] = {}
        self._consolidated_secret = consolidated_secret
        self._fallback_to_individual = fallback_to_individual
        self._consolidated_loaded = False
        self._consolidated_load_error: Optional[RuntimeError] = None
        self._consolidated_keys: set[str] = set()
        self._consolidated_key_count = 0
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

    def _access(self, key: str, *, warn_not_found: bool = True) -> Optional[str]:
        """Fetch one secret payload, or None when the secret does not exist."""
        name = self._secret_resource(key)

        try:
            response = self._client.access_secret_version(
                name=name, timeout=self._timeout, retry=self._retry
            )
        except gcp_exceptions.NotFound:
            if warn_not_found:
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
        if self._consolidated_loaded:
            if self._consolidated_load_error is not None:
                raise self._consolidated_load_error
            return
        if not self._consolidated_secret:
            return

        payload = self._access(self._consolidated_secret, warn_not_found=False)
        self._consolidated_loaded = True
        if payload is None:
            if not self._fallback_to_individual:
                error = RuntimeError(
                    f"Consolidated secret '{self._consolidated_secret}' not found "
                    f"in GCP project '{self._project_id}' and individual fallback "
                    "is disabled."
                )
                self._consolidated_load_error = error
                raise error
            logger.warning(
                f"Consolidated secret '{self._consolidated_secret}' not found; "
                "falling back to individual secret lookups."
            )
            return
        try:
            data = json.loads(payload)
        except ValueError:
            if not self._fallback_to_individual:
                error = RuntimeError(
                    f"Consolidated secret '{self._consolidated_secret}' is not valid "
                    "JSON and individual fallback is disabled."
                )
                self._consolidated_load_error = error
                raise error
            logger.warning(
                f"Consolidated secret '{self._consolidated_secret}' is not valid "
                "JSON; falling back to individual secret lookups."
            )
            return
        if not isinstance(data, dict):
            if not self._fallback_to_individual:
                error = RuntimeError(
                    f"Consolidated secret '{self._consolidated_secret}' must be a "
                    "JSON object and individual fallback is disabled."
                )
                self._consolidated_load_error = error
                raise error
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
        self._consolidated_keys = set(data)
        self._consolidated_key_count = len(data)
        logger.info(
            f"Preloaded {len(data)} values from consolidated secret "
            f"'{self._consolidated_secret}'."
        )

    def get(self, key: str) -> Optional[str]:
        self._preload_consolidated()

        if key in self._cache:
            return self._cache[key]

        if not self._fallback_to_individual:
            return None

        payload = self._access(key)
        self._cache[key] = payload
        return payload

    def get_many(self, keys: list[str]) -> dict[str, Optional[str]]:
        unique_keys = list(dict.fromkeys(keys))
        self._preload_consolidated()

        resolved_from_consolidated = sum(
            key in self._consolidated_keys for key in unique_keys
        )
        individual_accesses = 0
        values: dict[str, Optional[str]] = {}
        for key in unique_keys:
            if key in self._cache:
                values[key] = self._cache[key]
                continue
            if not self._fallback_to_individual:
                values[key] = None
                continue
            individual_accesses += 1
            payload = self._access(key, warn_not_found=False)
            self._cache[key] = payload
            values[key] = payload

        missing = sum(value is None for value in values.values())
        summary = (
            "GCP secret load summary: "
            f"preloaded={self._consolidated_key_count}, "
            f"resolved_from_consolidated={resolved_from_consolidated}, "
            f"individual_accesses={individual_accesses}, missing={missing}, "
            f"fallback_to_individual={str(self._fallback_to_individual).lower()}."
        )
        if (
            individual_accesses
            or missing
            or resolved_from_consolidated != len(unique_keys)
        ):
            logger.warning(summary)
        else:
            logger.info(summary)
        return values

    @property
    def project_id(self) -> str:
        """Return the configured GCP project identifier."""

        return self._project_id
