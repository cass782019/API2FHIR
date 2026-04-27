from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Endpoint

# Keyword → probable FHIR resource type(s)
_FHIR_KEYWORDS: dict[str, list[str]] = {
    "patient": ["Patient"],
    "paciente": ["Patient"],
    "encounter": ["Encounter"],
    "atendimento": ["Encounter"],
    "consulta": ["Encounter"],
    "observation": ["Observation"],
    "observacao": ["Observation"],
    "observação": ["Observation"],
    "lab": ["Observation", "DiagnosticReport"],
    "exam": ["Observation", "DiagnosticReport"],
    "exame": ["Observation", "DiagnosticReport"],
    "diagnostic": ["DiagnosticReport"],
    "diagnostico": ["DiagnosticReport"],
    "diagnóstico": ["DiagnosticReport"],
    "condition": ["Condition"],
    "problema": ["Condition"],
    "diagnosis": ["Condition"],
    "diagnose": ["Condition"],
    "medication": ["MedicationRequest"],
    "medicamento": ["MedicationRequest"],
    "prescri": ["MedicationRequest"],  # prefix: prescrição, prescricao
    "drug": ["MedicationRequest"],
    "procedure": ["Procedure"],
    "procedimento": ["Procedure"],
    "allergy": ["AllergyIntolerance"],
    "alergia": ["AllergyIntolerance"],
    "immuniz": ["Immunization"],  # prefix: immunization, imunização
    "vacin": ["Immunization"],  # prefix: vacina, vacinação
    "practitioner": ["Practitioner"],
    "medico": ["Practitioner"],
    "médico": ["Practitioner"],
    "doctor": ["Practitioner"],
    "organization": ["Organization"],
    "hospital": ["Organization"],
    "clinica": ["Organization"],
    "clínica": ["Organization"],
    "location": ["Location"],
    "bundle": ["Bundle"],
    "composition": ["Composition"],
    "document": ["Composition"],
    "device": ["Device"],
}


def extract_fhir_hints(endpoint: Endpoint) -> list[str]:
    """Infer probable FHIR resource types from endpoint metadata.

    Searches path, operationId, summary, description, and tags for known
    keywords. Returns a deduplicated list of FHIR resource type strings.
    """
    corpus = " ".join(
        [
            endpoint.path,
            endpoint.operation_id,
            endpoint.summary,
            endpoint.description,
            " ".join(endpoint.tags),
        ]
    ).lower()

    found: list[str] = []
    seen: set[str] = set()

    for keyword, resource_types in _FHIR_KEYWORDS.items():
        if keyword in corpus:
            for rt in resource_types:
                if rt not in seen:
                    found.append(rt)
                    seen.add(rt)

    return found
