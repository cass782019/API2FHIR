"""FHIR-Forge MCP Server.

Exposes 6 tools for Claude to interact with the FHIR stack at runtime:
  HAPI (4): validate_resource, get_resource, search_resources, expand_valueset
  Snowstorm (2): find_concept, translate_code

Start with:
    uv run python -m mcp_server.server

Or via FastAPI (when FEATURE_MCP_ENABLED=true):
    The apps/api router mounts this at /mcp.
"""
from __future__ import annotations

from fastmcp import FastMCP

from .settings import settings
from .tools.hapi import (
    expand_valueset,
    get_resource,
    search_resources,
    validate_resource,
)
from .tools.snowstorm import find_concept, translate_code

mcp = FastMCP("fhir-forge")

# ── HAPI FHIR tools ──────────────────────────────────────────────────────────

mcp.tool()(validate_resource)
mcp.tool()(get_resource)
mcp.tool()(search_resources)
mcp.tool()(expand_valueset)

# ── Snowstorm / Terminology tools ─────────────────────────────────────────────

mcp.tool()(find_concept)
mcp.tool()(translate_code)


if __name__ == "__main__":
    import uvicorn

    app = mcp.http_app(path="/mcp")
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
