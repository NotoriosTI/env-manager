"""Timeout y taxonomía de errores del loader de GCP (blueprint §1.5.3, §1.5.4)."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions

from env_manager.loaders.gcp import (
    DEFAULT_GCP_TIMEOUT,
    MAX_RETRY_ATTEMPTS,
    GCPSecretLoader,
    _is_transient,
    _resolve_timeout,
)


@pytest.fixture
def loader():
    with patch("env_manager.loaders.gcp.secretmanager.SecretManagerServiceClient"):
        yield GCPSecretLoader("proj")


class TestTimeoutResolution:
    def test_default_when_nothing_provided(self, monkeypatch):
        monkeypatch.delenv("ENV_MANAGER_GCP_TIMEOUT", raising=False)
        assert _resolve_timeout(None) == DEFAULT_GCP_TIMEOUT

    def test_explicit_argument_wins(self, monkeypatch):
        monkeypatch.setenv("ENV_MANAGER_GCP_TIMEOUT", "99")
        assert _resolve_timeout(2.5) == 2.5

    def test_env_var_used_when_no_argument(self, monkeypatch):
        monkeypatch.setenv("ENV_MANAGER_GCP_TIMEOUT", "3.5")
        assert _resolve_timeout(None) == 3.5

    @pytest.mark.parametrize("raw", ["abc", "0", "-1"])
    def test_invalid_env_var_falls_back_to_default(self, monkeypatch, raw):
        monkeypatch.setenv("ENV_MANAGER_GCP_TIMEOUT", raw)
        assert _resolve_timeout(None) == DEFAULT_GCP_TIMEOUT

    def test_loader_exposes_timeout(self, loader):
        assert loader.timeout == DEFAULT_GCP_TIMEOUT


class TestRetryPredicate:
    @pytest.mark.parametrize(
        "exc",
        [
            gcp_exceptions.ServiceUnavailable("x"),
            gcp_exceptions.DeadlineExceeded("x"),
            gcp_exceptions.TooManyRequests("x"),
            gcp_exceptions.InternalServerError("x"),
            gcp_exceptions.Aborted("x"),
        ],
    )
    def test_transient_errors_are_retried(self, exc):
        assert _is_transient(exc) is True

    @pytest.mark.parametrize(
        "exc",
        [
            gcp_exceptions.PermissionDenied("x"),
            gcp_exceptions.Unauthenticated("x"),
            gcp_exceptions.InvalidArgument("x"),
            gcp_exceptions.FailedPrecondition("x"),
            gcp_exceptions.NotFound("x"),
        ],
    )
    def test_deterministic_errors_are_not_retried(self, exc):
        assert _is_transient(exc) is False


class TestAccessCall:
    def test_every_call_carries_timeout_and_retry(self, loader):
        response = MagicMock()
        response.payload.data = b"value"
        loader._client.access_secret_version = MagicMock(return_value=response)

        assert loader.get("KEY") == "value"

        _, kwargs = loader._client.access_secret_version.call_args
        assert kwargs["timeout"] == DEFAULT_GCP_TIMEOUT
        assert kwargs["retry"] is loader._retry

    def test_not_found_returns_none(self, loader):
        loader._client.access_secret_version = MagicMock(
            side_effect=gcp_exceptions.NotFound("nope")
        )
        assert loader.get("KEY") is None

    def test_deterministic_error_says_retrying_will_not_help(self, loader):
        loader._client.access_secret_version = MagicMock(
            side_effect=gcp_exceptions.PermissionDenied("denied")
        )
        with pytest.raises(RuntimeError, match="Retrying will not help"):
            loader.get("KEY")

    def test_retry_exhaustion_reports_the_budget(self, loader):
        loader._client.access_secret_version = MagicMock(
            side_effect=gcp_exceptions.RetryError("exhausted", cause=None)
        )
        expected = f"{DEFAULT_GCP_TIMEOUT * MAX_RETRY_ATTEMPTS:.1f}s"
        with pytest.raises(RuntimeError, match=f"Retries exhausted after {expected}"):
            loader.get("KEY")
