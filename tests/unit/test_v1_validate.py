from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_valid_spec_via_endpoint(api_client) -> None:
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "0.1.0"},
        "paths": {},
    }
    r = await api_client.post("/v1/validate-spec", json={"spec": spec})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_missing_paths_returns_invalid(api_client) -> None:
    r = await api_client.post("/v1/validate-spec", json={"spec": {"openapi": "3.0.3"}})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1
