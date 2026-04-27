from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_noauth() -> TestClient:
    """Client with FEATURE_ADMIN_NOAUTH=True (default in test settings)."""
    from api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def client_auth() -> TestClient:
    """Client with FEATURE_ADMIN_NOAUTH=False — auth is enforced."""
    from unittest.mock import patch

    from api.main import create_app

    with patch("core.settings.settings") as mock_settings:
        mock_settings.feature_admin_noauth = False
        mock_settings.log_level = "DEBUG"
        mock_settings.env = "test"
        mock_settings.hapi_base_url = "http://localhost:8090/fhir"
        mock_settings.redis_url = "redis://localhost:6379"
        mock_settings.postgres_dsn = "postgresql+psycopg://localhost/forge"
        mock_settings.feature_mcp_enabled = False
        yield TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_health_accessible_without_auth(client_noauth: TestClient) -> None:
    """Health endpoint is public (no auth dependency)."""
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_ok())),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_ok())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_ok())),
    ):
        resp = client_noauth.get("/health")
    assert resp.status_code == 200


@pytest.mark.unit
def test_convert_bypassed_when_admin_noauth(client_noauth: TestClient) -> None:
    """With ADMIN_NOAUTH=True, no token needed for /convert."""
    with (
        patch("api.routers.convert.parse_spec", return_value=_mock_spec()),
        patch("api.routers.convert.convert", new=AsyncMock(return_value=_bundle())),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=_mock_client()),
    ):
        resp = client_noauth.post("/convert", json={"spec": "openapi: '3.0.3'\ninfo:\n  title: T\n  version: '1'\npaths: {}"})
    assert resp.status_code == 200


@pytest.mark.unit
def test_convert_requires_bearer_when_noauth_false() -> None:
    """When ADMIN_NOAUTH=False and no token, /convert returns 401."""
    from unittest.mock import MagicMock, patch

    from api.main import create_app
    from core.settings import Settings

    mock_settings = MagicMock(spec=Settings)
    mock_settings.feature_admin_noauth = False
    mock_settings.log_level = "DEBUG"
    mock_settings.env = "test"
    mock_settings.hapi_base_url = "http://localhost:8090/fhir"
    mock_settings.redis_url = "redis://localhost:6379"
    mock_settings.postgres_dsn = "postgresql+psycopg://localhost/forge"
    mock_settings.feature_mcp_enabled = False

    with patch("api.auth.settings", mock_settings):
        test_client = TestClient(create_app(), raise_server_exceptions=False)
        resp = test_client.post("/convert", json={"spec": "x: y"})

    assert resp.status_code == 401


@pytest.mark.unit
def test_convert_accepts_valid_token() -> None:
    """When ADMIN_NOAUTH=False and valid dev token provided, /convert proceeds."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from api.main import create_app

    auth_settings = MagicMock()
    auth_settings.feature_admin_noauth = False

    with (
        patch("api.auth.settings", auth_settings),
        patch("api.routers.convert.parse_spec", return_value=_mock_spec()),
        patch("api.routers.convert.convert", new=AsyncMock(return_value=_bundle())),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=_mock_client()),
    ):
        test_client = TestClient(create_app(), raise_server_exceptions=False)
        resp = test_client.post(
            "/convert",
            json={"spec": "openapi: '3.0.3'\ninfo:\n  title: T\n  version: '1'\npaths: {}"},
            headers={"Authorization": "Bearer dev-token"},
        )

    assert resp.status_code == 200


@pytest.mark.unit
def test_convert_rejects_invalid_token() -> None:
    """Invalid token returns 401."""
    from unittest.mock import MagicMock, patch

    from api.main import create_app
    from core.settings import Settings

    mock_settings = MagicMock(spec=Settings)
    mock_settings.feature_admin_noauth = False

    with patch("api.auth.settings", mock_settings):
        test_client = TestClient(create_app(), raise_server_exceptions=False)
        resp = test_client.post(
            "/convert",
            json={"spec": "x: y"},
            headers={"Authorization": "Bearer bad-token-xyz"},
        )

    assert resp.status_code == 401


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _ok() -> object:
    from api.schemas import ServiceStatus
    return ServiceStatus(ok=True)


def _mock_spec() -> object:
    from unittest.mock import MagicMock
    return MagicMock()


def _bundle() -> dict:
    return {"resourceType": "Bundle", "type": "collection", "entry": []}


def _mock_client() -> object:
    from unittest.mock import MagicMock
    return MagicMock()
