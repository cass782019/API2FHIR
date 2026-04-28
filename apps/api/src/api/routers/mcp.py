from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/mcp", tags=["mcp"])


def mount_mcp(app: Any) -> None:
    """Mount the MCP server under /mcp if FEATURE_MCP_ENABLED is set."""
    from core.settings import settings

    if not settings.feature_mcp_enabled:
        return

    try:
        from mcp_server.server import mcp  # type: ignore[import-not-found]

        mcp_app = mcp.streamable_http_app()
        app.mount("/mcp", mcp_app)
    except (ImportError, AttributeError) as exc:
        import structlog

        log = structlog.get_logger(__name__)
        log.warning("mcp_server_not_available", error=str(exc))
