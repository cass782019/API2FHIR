"""Session-scoped test fixtures for the fhir-forge test suite.

Testcontainers are started once per pytest session and shared across all
integration tests. Unit tests do not use these fixtures.

Usage in tests:
    @pytest.mark.integration
    async def test_something(hapi_base_url: str, postgres_url: str) -> None:
        ...
"""
from __future__ import annotations

import os
from collections.abc import Generator

import pytest

# ── Postgres ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL 16 container for the test session."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed — run `uv sync --all-extras --dev`")

    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def postgres_url(postgres_container) -> str:
    """Return the DSN for the session-scoped Postgres container."""
    return postgres_container.get_connection_url()


# ── Redis ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis 7.4 container for the test session."""
    try:
        from testcontainers.redis import RedisContainer
    except ImportError:
        pytest.skip("testcontainers not installed — run `uv sync --all-extras --dev`")

    with RedisContainer("redis:7.4-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    """Return the Redis URL for the session-scoped Redis container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


# ── HAPI FHIR ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def hapi_container():
    """Start a HAPI FHIR R4 container for the test session.

    Waits until the /fhir/metadata endpoint responds before yielding.
    Takes ~90s on first run; the container image is cached by Docker.
    """
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        pytest.skip("testcontainers not installed")

    container = (
        DockerContainer("hapiproject/hapi:v8.4.0-2")
        .with_env("hapi.fhir.fhir_version", "R4")
        .with_env("hapi.fhir.validation.requests_enabled", "true")
        .with_exposed_ports(8080)
    )

    with container:
        import time
        import httpx

        host = container.get_container_host_ip()
        port = container.get_exposed_port(8080)
        base_url = f"http://{host}:{port}/fhir"

        # Wait until HAPI is ready (up to 3 minutes)
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                r = httpx.get(f"{base_url}/metadata", timeout=5)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(5)
        else:
            pytest.fail("HAPI FHIR container did not become healthy within 3 minutes")

        container._hapi_base_url = base_url
        yield container


@pytest.fixture(scope="session")
def hapi_base_url(hapi_container) -> str:
    """Return the FHIR base URL for the session-scoped HAPI container."""
    return hapi_container._hapi_base_url


# ── Environment overrides ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_settings_from_containers(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Patch pydantic-settings URLs to point at testcontainers when in integration tests.

    Only active when the test explicitly requests container fixtures.
    """
    # Only patch if this test uses container fixtures
    uses_hapi = "hapi_base_url" in request.fixturenames
    uses_redis = "redis_url" in request.fixturenames
    uses_postgres = "postgres_url" in request.fixturenames

    original_env = {}

    if uses_hapi and "hapi_base_url" in request.fixturenames:
        # hapi_base_url is resolved via fixture — settings patching happens in tests
        pass

    yield

    # Restore
    for key, val in original_env.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture
async def api_client():
    """AsyncClient pré-configurado contra o app FastAPI (sem rede)."""
    import httpx

    from api.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Pytest markers ────────────────────────────────────────────────────────────

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: pure unit tests, no I/O")
    config.addinivalue_line("markers", "integration: requires testcontainers")
    config.addinivalue_line("markers", "regression: golden-file comparison tests")
    config.addinivalue_line("markers", "e2e: end-to-end saga tests, slow")
    config.addinivalue_line("markers", "rnds: requires RNDS sandbox credentials in env")
    config.addinivalue_line("markers", "slow: takes >5s")


# ── Skip RNDS tests without credentials ──────────────────────────────────────

def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-skip @pytest.mark.rnds tests if RNDS_CERT_PATH not in env."""
    rnds_cert = os.environ.get("RNDS_CERT_PATH")
    skip_rnds = pytest.mark.skip(reason="RNDS_CERT_PATH not set — skipping RNDS tests")

    for item in items:
        if item.get_closest_marker("rnds") and not rnds_cert:
            item.add_marker(skip_rnds)
