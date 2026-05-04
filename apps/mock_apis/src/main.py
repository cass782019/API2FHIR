"""Hospital Mock APIs — serve jsonAPI/ fixtures como endpoints HTTP reais."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

_data_env = os.getenv("MOCK_DATA_DIR")
_DATA = Path(_data_env) if _data_env else Path(__file__).parents[4] / "jsonAPI"

app = FastAPI(title="Hospital Mock APIs", version="1.0.0")


def _load(name: str) -> dict | list:
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


_APPOINTMENTS = {
    "results": [
        {
            "id": "APT-001",
            "encounterNumber": "ENC-12345",
            "appointmentDate": "2026-05-10T09:00:00",
            "status": "scheduled",
            "patient": {"id": 667, "name": "Paciente Exemplo"},
            "physician": {"code": 1, "name": "Dr. Exemplo"},
            "specialty": {"code": 22, "description": "Cardiologia"},
        }
    ],
    "total": 1,
}

_PHYSICIANS = {
    "results": [
        {
            "physicianCode": 1,
            "physicianName": "Dr. Exemplo",
            "physicianIsActive": True,
            "physicianIsOpenSchedule": True,
            "specialty": {"code": 22, "description": "Cardiologia"},
        }
    ],
    "total": 1,
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "apis": 5}


@app.get("/api/natural-person/{person_id}")
def natural_person(person_id: str) -> JSONResponse:
    return JSONResponse(_load("natural_person_response.json"))


@app.get("/api/insurances")
def insurances(page: int = 0, size: int = 10) -> JSONResponse:
    return JSONResponse(_load("insurance_response.json"))


@app.get("/api/medical-specialties")
def medical_specialties() -> JSONResponse:
    return JSONResponse(_load("medialSpecialities_response.json"))


@app.get("/api/schedules/appointments")
def schedules_appointments() -> dict:
    return _APPOINTMENTS


@app.get("/api/schedules/physicians")
def schedules_physicians() -> dict:
    return _PHYSICIANS


@app.get("/api/schedules/openapi.json")
def schedules_openapi() -> JSONResponse:
    return JSONResponse(_load("schedules_1.json"))
