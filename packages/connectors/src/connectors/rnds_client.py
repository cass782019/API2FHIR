from __future__ import annotations

import datetime as dt
import ssl
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_TOKEN_EXPIRY_BUFFER_SECS = 30


class RndsClient:
    """Client for the RNDS (Registro Nacional de Dados em Saúde) API.

    Authenticates via mTLS using a PKCS#12 (.pfx) certificate and
    caches the OAuth2 bearer token until near expiry.
    """

    def __init__(
        self,
        base_url: str,
        auth_url: str,
        cert_path: str | Path,
        cert_password: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_url = auth_url.rstrip("/")
        self._cert_path = Path(cert_path)
        self._cert_password = cert_password
        self._timeout = timeout

        self._token: str | None = None
        self._token_expires_at: dt.datetime | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.load_cert_chain(
            certfile=str(self._cert_path),
            password=self._cert_password,
        )
        return ctx

    def _is_token_valid(self) -> bool:
        if self._token is None or self._token_expires_at is None:
            return False
        return dt.datetime.now(tz=dt.UTC) < self._token_expires_at - dt.timedelta(
            seconds=_TOKEN_EXPIRY_BUFFER_SECS
        )

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    async def get_token(self) -> str:
        """Return a valid bearer token, fetching a new one when necessary."""
        if self._is_token_valid():
            return self._token  # type: ignore[return-value]

        ssl_ctx = self._build_ssl_context()
        async with httpx.AsyncClient(verify=ssl_ctx, timeout=self._timeout) as http:
            resp = await http.get(f"{self._auth_url}/token")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        self._token = data["access_token"]
        expires_in: int = data.get("expires_in", 3600)
        self._token_expires_at = dt.datetime.now(tz=dt.UTC) + dt.timedelta(seconds=expires_in)
        log.info("rnds_token_refreshed", expires_in=expires_in)
        return self._token

    # ------------------------------------------------------------------ #
    # Document operations
    # ------------------------------------------------------------------ #

    async def submit_document(self, document: dict[str, Any]) -> str:
        """Submit a FHIR document Bundle to RNDS and return the protocol ID."""
        token = await self.get_token()
        ssl_ctx = self._build_ssl_context()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/fhir+json",
        }
        async with httpx.AsyncClient(verify=ssl_ctx, timeout=self._timeout) as http:
            resp = await http.post(
                f"{self._base_url}/Bundle",
                json=document,
                headers=headers,
            )
        resp.raise_for_status()
        # RNDS returns the protocol/identifier in a custom header or body
        location: str = resp.headers.get("Location", "")
        if location:
            return str(location.rsplit("/", 1)[-1])
        data: dict[str, Any] = resp.json()
        return str(data.get("id", ""))

    async def get_document(self, protocol_id: str) -> dict[str, Any]:
        """Retrieve a previously submitted document by protocol ID."""
        token = await self.get_token()
        ssl_ctx = self._build_ssl_context()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(verify=ssl_ctx, timeout=self._timeout) as http:
            resp = await http.get(
                f"{self._base_url}/Bundle/{protocol_id}",
                headers=headers,
            )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
