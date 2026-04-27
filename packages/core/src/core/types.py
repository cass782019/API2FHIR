from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import ulid  # ulid-py: import is `ulid`, method is ulid.new()


class ResourceType(StrEnum):
    """FHIR R4 resource types used by fhir-forge."""

    PATIENT = "Patient"
    PRACTITIONER = "Practitioner"
    ORGANIZATION = "Organization"
    ENCOUNTER = "Encounter"
    OBSERVATION = "Observation"
    CONDITION = "Condition"
    MEDICATION_REQUEST = "MedicationRequest"
    DIAGNOSTIC_REPORT = "DiagnosticReport"
    PROCEDURE = "Procedure"
    ALLERGY_INTOLERANCE = "AllergyIntolerance"
    IMMUNIZATION = "Immunization"
    BUNDLE = "Bundle"
    COMPOSITION = "Composition"
    DEVICE = "Device"
    LOCATION = "Location"


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"


@dataclass
class Issue:
    severity: IssueSeverity
    code: str
    details: str
    location: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    issues: list[Issue] = field(default_factory=list)

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True, issues=[])

    def has_errors(self) -> bool:
        return any(
            i.severity in (IssueSeverity.ERROR, IssueSeverity.FATAL)
            for i in self.issues
        )


@dataclass
class ConversionJob:
    status: JobStatus
    id: str = field(default_factory=lambda: str(ulid.new()))
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC)
    )
    spec_hash: str | None = None
    error: str | None = None
