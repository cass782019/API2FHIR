from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_auth
from api.schemas import FetchUrlRequest, FetchUrlResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/fetch-url", tags=["v1"], dependencies=[Depends(require_auth)])

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("", response_model=FetchUrlResponse)
async def fetch_url(body: FetchUrlRequest) -> FetchUrlResponse:
    scheme = urlparse(body.url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=422,
            detail=f"URL scheme '{scheme}' not allowed — only http/https",
        )
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=body.timeout) as client:
            r = await client.request(
                body.method.upper(),
                body.url,
                headers=body.headers,
            )
            r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Remote returned {exc.response.status_code}: {body.url}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach {body.url}: {exc}",
        ) from exc

    from spec_inferer.detector import detect_spec_type

    content = r.text[:_MAX_BYTES]
    det = detect_spec_type(content)
    log.info("fetch_url_ok", url=body.url, type=det["type"])
    return FetchUrlResponse(
        content=content,
        type=det["type"],
        version=det.get("version"),
        url=body.url,
        content_type=r.headers.get("content-type", ""),
    )
