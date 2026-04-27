from __future__ import annotations

import httpx
import structlog

from .models import Coding

log = structlog.get_logger(__name__)


class HapiValueSetClient:
    """Client for HAPI FHIR ValueSet $expand and $lookup operations."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def expand(
        self,
        valueset_url: str,
        filter_text: str | None = None,
        count: int = 50,
    ) -> list[Coding]:
        """Expand a ValueSet and return all contained Codings."""
        params: dict[str, str | int] = {"url": valueset_url, "count": count}
        if filter_text:
            params["filter"] = filter_text

        url = f"{self._base_url}/ValueSet/$expand"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            log.warning("hapi_expand_error", valueset=valueset_url, status=exc.response.status_code)
            return []
        except httpx.RequestError as exc:
            log.warning("hapi_expand_request_error", valueset=valueset_url, error=str(exc))
            return []

        results: list[Coding] = []
        expansion = data.get("expansion", {})
        for entry in expansion.get("contains", []):
            system = entry.get("system", "")
            code = entry.get("code", "")
            display = entry.get("display", "")
            if system and code:
                results.append(Coding(system=system, code=code, display=display))
        return results

    async def lookup(self, system: str, code: str) -> Coding | None:
        """Look up a single code in a code system via $lookup."""
        url = f"{self._base_url}/CodeSystem/$lookup"
        params: dict[str, str] = {"system": system, "code": code}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            log.warning("hapi_lookup_error", system=system, code=code, status=exc.response.status_code)
            return None
        except httpx.RequestError as exc:
            log.warning("hapi_lookup_request_error", system=system, code=code, error=str(exc))
            return None

        # Parameters resource — find the "display" parameter
        display = ""
        for param in data.get("parameter", []):
            if param.get("name") == "display":
                display = param.get("valueString", "")
                break
        return Coding(system=system, code=code, display=display)
