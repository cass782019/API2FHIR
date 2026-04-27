from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
import respx
from httpx import Response

_RNDS_BASE = "https://ehr-auth.saude.gov.br/api"
_RNDS_FHIR = "https://ehr-services.saude.gov.br/api/fhir"
_CERT = "/fake/cert.pfx"
_PASSWORD = "secret"

_TOKEN_RESPONSE = {
    "access_token": "eyJhbGciOiJSUzI1NiJ9.fake",
    "token_type": "Bearer",
    "expires_in": 1800,
}

_BUNDLE = {
    "resourceType": "Bundle",
    "id": "bundle-001",
    "type": "document",
    "entry": [],
}


def _make_client() -> object:
    from connectors.rnds_client import RndsClient

    return RndsClient(
        base_url=_RNDS_FHIR,
        auth_url=_RNDS_BASE,
        cert_path=_CERT,
        cert_password=_PASSWORD,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_token_fetches_and_caches() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        respx.get(f"{_RNDS_BASE}/token").mock(return_value=Response(200, json=_TOKEN_RESPONSE))
        client = _make_client()
        token = await client.get_token()  # type: ignore[union-attr]

    assert token == _TOKEN_RESPONSE["access_token"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_token_uses_cache_on_second_call() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        route = respx.get(f"{_RNDS_BASE}/token").mock(
            return_value=Response(200, json=_TOKEN_RESPONSE)
        )
        client = _make_client()
        await client.get_token()  # type: ignore[union-attr]
        await client.get_token()  # second call — should use cache

    assert route.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_token_refreshes_when_expired() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        route = respx.get(f"{_RNDS_BASE}/token").mock(
            return_value=Response(200, json=_TOKEN_RESPONSE)
        )
        client = _make_client()
        # type: ignore
        await client.get_token()  # type: ignore[union-attr]
        # Force expiry
        client._token_expires_at = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=1)  # type: ignore[union-attr]
        await client.get_token()  # type: ignore[union-attr]

    assert route.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_document_returns_protocol_from_location_header() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        respx.get(f"{_RNDS_BASE}/token").mock(return_value=Response(200, json=_TOKEN_RESPONSE))
        respx.post(f"{_RNDS_FHIR}/Bundle").mock(
            return_value=Response(
                201,
                headers={"Location": f"{_RNDS_FHIR}/Bundle/protocol-abc123"},
                json=_BUNDLE,
            )
        )
        client = _make_client()
        protocol_id = await client.submit_document(_BUNDLE)  # type: ignore[union-attr]

    assert protocol_id == "protocol-abc123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_document_returns_id_from_body_when_no_location() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        respx.get(f"{_RNDS_BASE}/token").mock(return_value=Response(200, json=_TOKEN_RESPONSE))
        respx.post(f"{_RNDS_FHIR}/Bundle").mock(
            return_value=Response(201, json={**_BUNDLE, "id": "bundle-xyz"})
        )
        client = _make_client()
        protocol_id = await client.submit_document(_BUNDLE)  # type: ignore[union-attr]

    assert protocol_id == "bundle-xyz"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_document_returns_bundle() -> None:
    from connectors.rnds_client import RndsClient

    with (
        patch.object(RndsClient, "_build_ssl_context", return_value=True),
        respx.mock,
    ):
        respx.get(f"{_RNDS_BASE}/token").mock(return_value=Response(200, json=_TOKEN_RESPONSE))
        respx.get(f"{_RNDS_FHIR}/Bundle/protocol-abc123").mock(
            return_value=Response(200, json=_BUNDLE)
        )
        client = _make_client()
        doc = await client.get_document("protocol-abc123")  # type: ignore[union-attr]

    assert doc["resourceType"] == "Bundle"


@pytest.mark.unit
def test_is_token_valid_returns_false_when_no_token() -> None:
    from connectors.rnds_client import RndsClient

    client = RndsClient(
        base_url=_RNDS_FHIR,
        auth_url=_RNDS_BASE,
        cert_path=_CERT,
        cert_password=_PASSWORD,
    )
    assert client._is_token_valid() is False


@pytest.mark.unit
def test_is_token_valid_returns_false_when_expired() -> None:
    from connectors.rnds_client import RndsClient

    client = RndsClient(
        base_url=_RNDS_FHIR,
        auth_url=_RNDS_BASE,
        cert_path=_CERT,
        cert_password=_PASSWORD,
    )
    client._token = "tok"
    client._token_expires_at = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=60)
    assert client._is_token_valid() is False


@pytest.mark.unit
def test_is_token_valid_returns_true_when_fresh() -> None:
    from connectors.rnds_client import RndsClient

    client = RndsClient(
        base_url=_RNDS_FHIR,
        auth_url=_RNDS_BASE,
        cert_path=_CERT,
        cert_password=_PASSWORD,
    )
    client._token = "tok"
    client._token_expires_at = dt.datetime.now(tz=dt.UTC) + dt.timedelta(seconds=900)
    assert client._is_token_valid() is True
