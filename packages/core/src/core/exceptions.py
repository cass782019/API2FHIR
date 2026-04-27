from __future__ import annotations

from typing import Any


class FhirForgeError(Exception):
    """Base exception for all fhir-forge errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = context or {}


class ValidationError(FhirForgeError):
    def __init__(
        self,
        message: str,
        resource_type: str = "",
        issues: list[str] | None = None,
    ) -> None:
        super().__init__(message, {"resource_type": resource_type, "issues": issues or []})
        self.resource_type = resource_type
        self.issues: list[str] = issues or []


class MappingError(FhirForgeError):
    def __init__(self, message: str, endpoint: str = "", reason: str = "") -> None:
        super().__init__(message, {"endpoint": endpoint, "reason": reason})
        self.endpoint = endpoint
        self.reason = reason


class TerminologyError(FhirForgeError):
    def __init__(self, message: str, system: str = "", code: str = "") -> None:
        super().__init__(message, {"system": system, "code": code})
        self.system = system
        self.code = code


class ConnectorError(FhirForgeError):
    def __init__(
        self,
        message: str,
        service: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, {"service": service, "status_code": status_code})
        self.service = service
        self.status_code = status_code


class ConfigurationError(FhirForgeError):
    """Raised when a required configuration value is missing or invalid."""
