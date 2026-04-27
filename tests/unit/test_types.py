from __future__ import annotations

import datetime as dt

import pytest


@pytest.mark.unit
def test_conversion_job_has_ulid_id() -> None:
    from core.types import ConversionJob, JobStatus

    job = ConversionJob(status=JobStatus.PENDING)
    assert isinstance(job.id, str)
    assert len(job.id) == 26  # ULID is always 26 chars


@pytest.mark.unit
def test_conversion_job_unique_ids() -> None:
    from core.types import ConversionJob, JobStatus

    j1 = ConversionJob(status=JobStatus.PENDING)
    j2 = ConversionJob(status=JobStatus.PENDING)
    assert j1.id != j2.id


@pytest.mark.unit
def test_conversion_job_created_at_is_utc() -> None:
    from core.types import ConversionJob, JobStatus

    job = ConversionJob(status=JobStatus.PENDING)
    assert job.created_at.tzinfo is not None  # timezone-aware
    assert job.created_at.utcoffset() == dt.timedelta(0)  # UTC offset is zero


@pytest.mark.unit
def test_conversion_job_optional_fields_none_by_default() -> None:
    from core.types import ConversionJob, JobStatus

    job = ConversionJob(status=JobStatus.PENDING)
    assert job.spec_hash is None
    assert job.error is None


@pytest.mark.unit
def test_conversion_job_status_transitions() -> None:
    from core.types import ConversionJob, JobStatus

    job = ConversionJob(status=JobStatus.PENDING)
    assert job.status == JobStatus.PENDING
    job.status = JobStatus.PROCESSING
    assert job.status == JobStatus.PROCESSING


@pytest.mark.unit
def test_validation_result_ok_is_valid() -> None:
    from core.types import ValidationResult

    r = ValidationResult.ok()
    assert r.valid is True
    assert r.issues == []
    assert r.has_errors() is False


@pytest.mark.unit
def test_validation_result_with_error_has_errors() -> None:
    from core.types import Issue, IssueSeverity, ValidationResult

    issue = Issue(severity=IssueSeverity.ERROR, code="required", details="missing name")
    r = ValidationResult(valid=False, issues=[issue])
    assert r.has_errors() is True


@pytest.mark.unit
def test_validation_result_with_fatal_has_errors() -> None:
    from core.types import Issue, IssueSeverity, ValidationResult

    issue = Issue(severity=IssueSeverity.FATAL, code="invalid", details="critical")
    r = ValidationResult(valid=False, issues=[issue])
    assert r.has_errors() is True


@pytest.mark.unit
def test_validation_result_warning_only_no_errors() -> None:
    from core.types import Issue, IssueSeverity, ValidationResult

    issue = Issue(severity=IssueSeverity.WARNING, code="best-practice", details="...")
    r = ValidationResult(valid=True, issues=[issue])
    assert r.has_errors() is False


@pytest.mark.unit
def test_validation_result_information_only_no_errors() -> None:
    from core.types import Issue, IssueSeverity, ValidationResult

    issue = Issue(severity=IssueSeverity.INFORMATION, code="info", details="note")
    r = ValidationResult(valid=True, issues=[issue])
    assert r.has_errors() is False


@pytest.mark.unit
def test_issue_default_location_empty() -> None:
    from core.types import Issue, IssueSeverity

    issue = Issue(severity=IssueSeverity.ERROR, code="required", details="missing")
    assert issue.location == []


@pytest.mark.unit
def test_issue_with_location() -> None:
    from core.types import Issue, IssueSeverity

    issue = Issue(
        severity=IssueSeverity.ERROR,
        code="required",
        details="missing",
        location=["Patient.name"],
    )
    assert "Patient.name" in issue.location


@pytest.mark.unit
def test_resource_type_enum_values() -> None:
    from core.types import ResourceType

    assert ResourceType.PATIENT == "Patient"
    assert ResourceType.BUNDLE == "Bundle"
    assert ResourceType.OBSERVATION == "Observation"
    assert ResourceType.ENCOUNTER == "Encounter"
    assert ResourceType.CONDITION == "Condition"


@pytest.mark.unit
def test_resource_type_is_str() -> None:
    from core.types import ResourceType

    assert isinstance(ResourceType.PATIENT, str)
    assert f"type={ResourceType.PATIENT}" == "type=Patient"


@pytest.mark.unit
def test_job_status_enum_values() -> None:
    from core.types import JobStatus

    assert JobStatus.PENDING == "pending"
    assert JobStatus.PROCESSING == "processing"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.FAILED == "failed"
