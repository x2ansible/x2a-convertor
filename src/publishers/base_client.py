"""Base HTTP client for AAP APIs.

Provides common session management, authentication, and SSL handling
for both Controller and Galaxy API clients.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests

from src.config import AAPSettings, get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BaseAAPClient(ABC):
    """Base client with shared HTTP session, auth, and SSL configuration.

    Subclasses must implement:
    - _base_url: The base URL for API requests
    - _api_prefix: The API path prefix
    - _auth_header_format: "Bearer" or "Token" for the Authorization header
    """

    def __init__(self, settings: AAPSettings | None = None) -> None:
        self._settings = settings or get_settings().aap
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._setup_auth()

    @property
    @abstractmethod
    def _base_url(self) -> str:
        """Return the base URL for this API."""

    @property
    @abstractmethod
    def _api_prefix(self) -> str:
        """Return the API path prefix (e.g., /api/controller/v2)."""

    @property
    def _auth_header_format(self) -> str:
        """Return the auth header format. Override for Token auth."""
        return "Bearer"

    def _setup_auth(self) -> None:
        """Configure authentication on the session."""
        if self._settings.oauth_token:
            token = self._settings.oauth_token.get_secret_value()
            self._session.headers["Authorization"] = (
                f"{self._auth_header_format} {token}"
            )

    @property
    def _verify(self) -> bool | str:
        """Return SSL verification setting (bool or CA bundle path)."""
        if self._settings.ca_bundle:
            return self._settings.ca_bundle
        return self._settings.verify_ssl

    @property
    def _timeout(self) -> float:
        """Return request timeout in seconds."""
        return self._settings.timeout_s

    def _url(self, path: str) -> str:
        """Build full URL from base URL and path."""
        base = self._base_url.rstrip("/")
        p = path if path.startswith("/") else f"/{path}"
        return f"{base}{p}"

    def _api(self, path: str) -> str:
        """Build API path with prefix."""
        p = path if path.startswith("/") else f"/{path}"
        return f"{self._api_prefix}{p}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        use_full_url: bool = False,
    ) -> dict[str, Any]:
        """Execute HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            path: API path (will be prefixed with _api_prefix unless use_full_url=True)
            json: Request body as JSON
            params: Query parameters
            use_full_url: If True, treat path as a complete URL (for pagination)

        Returns:
            Response JSON as dict
        """
        url = path if use_full_url else self._url(self._api(path))

        resp = self._session.request(
            method=method,
            url=url,
            auth=self._get_basic_auth(),
            json=json,
            params=params,
            verify=self._verify,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _get_basic_auth(self) -> tuple[str, str] | None:
        """Return basic auth credentials if OAuth token is not set."""
        if self._settings.oauth_token:
            return None

        username = self._settings.username
        password = self._settings.password
        if username and password:
            pw = password.get_secret_value()
            return (username, pw)

        return None
