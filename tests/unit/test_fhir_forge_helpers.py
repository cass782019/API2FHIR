from __future__ import annotations

import pytest


@pytest.mark.unit
def test_slugify_basic_lowercase() -> None:
    from fhir_forge.nodes._helpers import slugify

    assert slugify("bookTime") == "booktime"
    assert slugify("createPatient") == "createpatient"


@pytest.mark.unit
def test_slugify_replaces_underscore_and_space() -> None:
    from fhir_forge.nodes._helpers import slugify

    assert slugify("get_user_by_id") == "get-user-by-id"
    assert slugify("Schedule list view") == "schedule-list-view"


@pytest.mark.unit
def test_slugify_empty_returns_empty() -> None:
    from fhir_forge.nodes._helpers import slugify

    assert slugify("") == ""
    assert slugify("___") == ""


@pytest.mark.unit
def test_repair_mojibake_known_pattern() -> None:
    from fhir_forge.nodes._helpers import repair_mojibake

    assert repair_mojibake("Dr. JoÃ£o Santos") == "Dr. João Santos"
    assert repair_mojibake("Consulta mÃ©dica") == "Consulta médica"


@pytest.mark.unit
def test_repair_mojibake_clean_passthrough() -> None:
    from fhir_forge.nodes._helpers import repair_mojibake

    assert repair_mojibake("Dr. João") == "Dr. João"
    assert repair_mojibake("plain ascii") == "plain ascii"


@pytest.mark.unit
def test_repair_mojibake_falls_back_when_encode_fails() -> None:
    """Marker + caractere fora de Latin-1 (emoji): encode('latin-1') falha → retorna original."""
    from fhir_forge.nodes._helpers import repair_mojibake

    weird = "JoÃ£o 😀"  # tem marker + emoji (codepoint > 255)
    assert repair_mojibake(weird) == weird


@pytest.mark.unit
def test_sanitize_resource_nested() -> None:
    from fhir_forge.nodes._helpers import sanitize_resource

    res = {
        "resourceType": "Practitioner",
        "name": [{"family": "JoÃ£o", "given": ["mÃ©dico"]}],
        "qualification": [{"code": {"text": "ok"}}],
    }
    out = sanitize_resource(res)
    assert out["name"][0]["family"] == "João"
    assert out["name"][0]["given"][0] == "médico"
    assert out["qualification"][0]["code"]["text"] == "ok"
    # input não é mutado
    assert res["name"][0]["family"] == "JoÃ£o"


@pytest.mark.unit
def test_sanitize_resource_preserves_non_string_leaves() -> None:
    """Valores não-string (int, bool, None) passam intactos pelo walk."""
    from fhir_forge.nodes._helpers import sanitize_resource

    res = {
        "resourceType": "Observation",
        "id": "x",
        "active": True,
        "valueInteger": 42,
        "note": None,
    }
    out = sanitize_resource(res)
    assert out["active"] is True
    assert out["valueInteger"] == 42
    assert out["note"] is None
