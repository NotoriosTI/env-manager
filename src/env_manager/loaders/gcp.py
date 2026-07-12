"""Loader implementation backed by Google Secret Manager."""

from __future__ import annotations

import json
from typing import Optional

from google.api_core import exceptions as gcp_exceptions
from google.cloud import secretmanager

from env_manager.base import SecretLoader

from env_manager.utils import logger


class GCPSecretLoader(SecretLoader):
    """Load secrets from GCP Secret Manager with simple caching.

    When ``consolidated_secret`` is set, that single secret is fetched once
    and must contain a JSON object; its entries pre-populate the cache so
    resolving each key costs zero extra API calls. Keys absent from the
    consolidated payload fall back to individual secret lookups.
    """

    def __init__(
        self, project_id: str, consolidated_secret: Optional[str] = None
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

    def _secret_resource(self, secret_name: str) -> str:
        return f"projects/{self._project_id}/secrets/{secret_name}/versions/latest"

    def _access(self, key: str) -> Optional[str]:
        """Fetch one secret payload, or None when the secret does not exist."""
        name = self._secret_resource(key)

        try:
            response = self._client.access_secret_version(name=name)
        except gcp_exceptions.NotFound:
            logger.warning(
                f"Secret '{key}' not found in GCP project '{self._project_id}'."
            )
            return None
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(
                "Failed to access secret "
                f"'{key}' in GCP project '{self._project_id}': {exc}"
            ) from exc
        except gcp_exceptions.RetryError as exc:  # pragma: no cover - seldom triggered
            raise RuntimeError(
                "Retry exhausted when accessing secret "
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
