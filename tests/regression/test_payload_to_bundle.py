"""Regression: a payload (não spec) flui pelo /v1/convert com auto_infer=true e
gera um Bundle FHIR estruturalmente válido (4 invariantes do v2.1)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PAYLOAD_PATH = (
    Path(__file__).parent.parent.parent / "data" / "golden" / "payloads" / "natural_person.json"
)

_UUID_V4_RE = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_MOJIBAKE_MARKERS = ("Ã£", "Ã©", "Ã§", "Ã³", "Ã­", "Ãº")


def _assert_structural_invariants(bundle: dict[str, Any]) -> None:
    """Mesma asserção de tests/regression/test_golden_bundles.py — duplicada aqui
    porque pytest não importa entre arquivos de teste sem package boilerplate."""
    entries = bundle.get("entry", [])
    bad_urls = [
        e["fullUrl"] for e in entries if not _UUID_V4_RE.match(e.get("fullUrl", ""))
    ]
    assert not bad_urls, f"Invalid fullUrls: {bad_urls[:3]}"
    ids = [e["resource"].get("id", "") for e in entries]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    assert not dups, f"Duplicate resource ids: {dups}"
    missing_narr = [
        e["resource"].get("id", "?")
        for e in entries
        if not (e["resource"].get("text") or {}).get("div")
    ]
    assert not missing_narr, f"Resources without text.div: {missing_narr[:3]}"
    blob = json.dumps(bundle, ensure_ascii=False)
    found = [m for m in _MOJIBAKE_MARKERS if m in blob]
    assert not found, f"Mojibake markers found: {found}"


def _mock_llm_returning(resource: dict) -> MagicMock:
    tb = MagicMock()
    tb.text = json.dumps(resource)
    msg = MagicMock()
    msg.content = [tb]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


@pytest.mark.regression
@pytest.mark.asyncio
async def test_payload_to_bundle_preserves_v2_1_invariants(api_client) -> None:
    """Payload (não spec) + auto_infer=true → Bundle com 4 invariantes."""
    payload_text = _PAYLOAD_PATH.read_text(encoding="utf-8")

    # Mock o cliente Anthropic que o /v1/convert vai criar internamente
    fake_client = _mock_llm_returning({
        "resourceType": "Patient",
        "id": "ignored-by-mapping-node",
        "gender": "male",
        "birthDate": "1991-04-15",
    })

    with (
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=fake_client),
        patch(
            "fhir_forge.nodes.validation_node._validate_resource",
            new=AsyncMock(return_value=[]),  # all valid
        ),
    ):
        r = await api_client.post(
            "/v1/convert",
            json={
                "spec": payload_text,
                "options": {
                    "async": False,
                    "auto_infer": True,
                    "hapi_base_url": "http://hapi.test/fhir",
                },
            },
        )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "completed"
    bundle = data["bundle"]
    assert bundle["resourceType"] == "Bundle"
    assert len(bundle["entry"]) >= 1, "Bundle deve ter ao menos 1 entry"
    # 4 invariantes estruturais (UUID v4 fullUrl, ids únicos, narrativa, sem mojibake)
    _assert_structural_invariants(bundle)
