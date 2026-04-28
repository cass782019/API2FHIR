from __future__ import annotations

import pytest
from swagger_lens.models import Endpoint


def _ep(**kwargs: str | list[str]) -> Endpoint:  # type: ignore[misc]
    defaults: dict[str, object] = {
        "path": "/",
        "method": "GET",
        "operation_id": "",
        "summary": "",
        "description": "",
        "tags": [],
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return Endpoint(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
def test_extract_patient_from_path() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/patients/{id}")
    hints = extract_fhir_hints(ep)
    assert "Patient" in hints


@pytest.mark.unit
def test_extract_patient_from_tag() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/people/{id}", tags=["patient"])
    hints = extract_fhir_hints(ep)
    assert "Patient" in hints


@pytest.mark.unit
def test_extract_encounter_from_operation_id() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(operation_id="listEncounters")
    hints = extract_fhir_hints(ep)
    assert "Encounter" in hints


@pytest.mark.unit
def test_extract_observation_from_summary() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(summary="Record clinical observation")
    hints = extract_fhir_hints(ep)
    assert "Observation" in hints


@pytest.mark.unit
def test_extract_medication_from_path() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/medications")
    hints = extract_fhir_hints(ep)
    assert "MedicationRequest" in hints


@pytest.mark.unit
def test_extract_portuguese_paciente() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/pacientes/{id}", tags=["paciente"])
    hints = extract_fhir_hints(ep)
    assert "Patient" in hints


@pytest.mark.unit
def test_extract_portuguese_exame() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/exames", summary="Listar exames laboratoriais")
    hints = extract_fhir_hints(ep)
    assert "Observation" in hints or "DiagnosticReport" in hints


@pytest.mark.unit
def test_extract_no_hints_for_unrelated_endpoint() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(path="/health", operation_id="healthCheck", summary="System health check")
    hints = extract_fhir_hints(ep)
    assert hints == []


@pytest.mark.unit
def test_extract_returns_deduplicated_list() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    # Both "patient" and "paciente" → Patient; should appear once
    ep = _ep(path="/patient", operation_id="getPaciente", tags=["patient", "paciente"])
    hints = extract_fhir_hints(ep)
    assert hints.count("Patient") == 1


@pytest.mark.unit
def test_extract_multiple_resource_types() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(
        path="/patient-encounters",
        operation_id="getPatientEncounters",
        tags=["patient", "encounter"],
    )
    hints = extract_fhir_hints(ep)
    assert "Patient" in hints
    assert "Encounter" in hints


@pytest.mark.unit
def test_extract_lab_tag_hints_observation_and_diagnostic() -> None:
    from swagger_lens.extractor import extract_fhir_hints

    ep = _ep(tags=["lab"])
    hints = extract_fhir_hints(ep)
    assert "Observation" in hints
    assert "DiagnosticReport" in hints
