from __future__ import annotations

from typing import Any

import httpx
import structlog
import tenacity
from core.types import Issue, IssueSeverity, ValidationResult

log = structlog.get_logger(__name__)

_DEFAULT_PAGE_SIZE = 50


def _parse_issues(outcome: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for raw in outcome.get("issue", []):
        try:
            severity = IssueSeverity(raw.get("severity", "information"))
        except ValueError:
            severity = IssueSeverity.INFORMATION
        issues.append(
            Issue(
                severity=severity,
                code=raw.get("code", "unknown"),
                details=raw.get("diagnostics", raw.get("details", {}).get("text", "")),
            )
        )
    return issues


class HapiFhirClient:
    """Async HAPI FHIR REST client with retry and structured error handling."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _url(self, resource_type: str, resource_id: str | None = None) -> str:
        if resource_id:
            return f"{self._base}/{resource_type}/{resource_id}"
        return f"{self._base}/{resource_type}"

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(min=1, max=10),
        reraise=True,
        retry=tenacity.retry_if_exception_type(httpx.TransportError),
    )
    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.request(method, url, json=json, params=params)
        return resp

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    async def create(self, resource: dict[str, Any]) -> dict[str, Any]:
        resource_type = resource.get("resourceType", "Resource")
        resp = await self._request("POST", self._url(resource_type), json=resource)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any] | None:
        resp = await self._request("GET", self._url(resource_type, resource_id))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def update(self, resource: dict[str, Any]) -> dict[str, Any]:
        resource_type = resource.get("resourceType", "Resource")
        resource_id = resource.get("id", "")
        resp = await self._request("PUT", self._url(resource_type, resource_id), json=resource)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def delete(self, resource_type: str, resource_id: str) -> None:
        resp = await self._request("DELETE", self._url(resource_type, resource_id))
        if resp.status_code not in (200, 204):
            resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Search (auto-pagination via Bundle links)
    # ------------------------------------------------------------------ #

    async def search(
        self,
        resource_type: str,
        params: dict[str, Any],
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        all_resources: list[dict[str, Any]] = []
        search_params = {**params, "_count": _DEFAULT_PAGE_SIZE}
        url: str | None = self._url(resource_type)

        for _ in range(max_pages):
            if url is None:
                break
            resp = await self._request("GET", url, params=search_params if url == self._url(resource_type) else None)
            resp.raise_for_status()
            bundle: dict[str, Any] = resp.json()
            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if resource:
                    all_resources.append(resource)
            # Follow "next" link for pagination
            url = None
            for link in bundle.get("link", []):
                if link.get("relation") == "next":
                    url = link.get("url")
                    break
            search_params = {}  # params already encoded in next URL

        return all_resources

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    async def validate(
        self,
        resource: dict[str, Any],
        profile: str | None = None,
    ) -> ValidationResult:
        resource_type = resource.get("resourceType", "Resource")
        url = f"{self._base}/{resource_type}/$validate"
        req_params: dict[str, str] = {}
        if profile:
            req_params["profile"] = profile
        resp = await self._request("POST", url, json=resource, params=req_params or None)
        # HAPI returns 200 or 422 for OperationOutcome
        outcome: dict[str, Any] = resp.json()
        issues = _parse_issues(outcome)
        has_error = any(i.severity in (IssueSeverity.ERROR, IssueSeverity.FATAL) for i in issues)
        return ValidationResult(valid=not has_error, issues=issues)
