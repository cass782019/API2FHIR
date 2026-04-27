from __future__ import annotations

import pytest


@pytest.mark.unit
def test_fhir_forge_error_is_exception() -> None:
    from core.exceptions import FhirForgeError

    e = FhirForgeError("test error")
    assert isinstance(e, Exception)
    assert str(e) == "test error"
    assert e.context == {}


@pytest.mark.unit
def test_fhir_forge_error_with_context() -> None:
    from core.exceptions import FhirForgeError

    e = FhirForgeError("test", context={"key": "value"})
    assert e.context["key"] == "value"


@pytest.mark.unit
def test_validation_error_has_resource_type() -> None:
    from core.exceptions import FhirForgeError, ValidationError

    e = ValidationError("invalid", resource_type="Patient", issues=["missing name"])
    assert isinstance(e, FhirForgeError)
    assert e.resource_type == "Patient"
    assert e.issues == ["missing name"]


@pytest.mark.unit
def test_validation_error_defaults() -> None:
    from core.exceptions import ValidationError

    e = ValidationError("invalid")
    assert e.resource_type == ""
    assert e.issues == []


@pytest.mark.unit
def test_mapping_error_has_endpoint() -> None:
    from core.exceptions import MappingError

    e = MappingError("failed", endpoint="/patients", reason="ambiguous schema")
    assert e.endpoint == "/patients"
    assert e.reason == "ambiguous schema"


@pytest.mark.unit
def test_terminology_error_has_system_and_code() -> None:
    from core.exceptions import TerminologyError

    e = TerminologyError("not found", system="http://snomed.info/sct", code="73211009")
    assert e.system == "http://snomed.info/sct"
    assert e.code == "73211009"


@pytest.mark.unit
def test_connector_error_has_service_and_status() -> None:
    from core.exceptions import ConnectorError

    e = ConnectorError("timeout", service="HAPI", status_code=503)
    assert e.service == "HAPI"
    assert e.status_code == 503


@pytest.mark.unit
def test_connector_error_optional_status() -> None:
    from core.exceptions import ConnectorError

    e = ConnectorError("connection refused", service="RNDS")
    assert e.status_code is None


@pytest.mark.unit
def test_all_errors_inherit_base() -> None:
    from core.exceptions import (
        ConfigurationError,
        ConnectorError,
        FhirForgeError,
        MappingError,
        TerminologyError,
        ValidationError,
    )

    for cls in [
        ValidationError,
        MappingError,
        TerminologyError,
        ConnectorError,
        ConfigurationError,
    ]:
        assert issubclass(cls, FhirForgeError)


@pytest.mark.unit
def test_configuration_error_message() -> None:
    from core.exceptions import ConfigurationError

    e = ConfigurationError("ANTHROPIC_API_KEY not set")
    assert "ANTHROPIC_API_KEY" in str(e)
