from pydantic import BaseModel
from typing import Any


class AnalyticsPayload(BaseModel):
    instrument_id: str
    timestamp: str
    readings: dict[str, Any]
    status: str = "nominal"


class InstrumentRegistration(BaseModel):
    instrument_id: str
    type: str
    name: str
    port: int
    capabilities: list[str] = []


class FinalizePayload(BaseModel):
    report: str
    outcome: str  # "success" | "partial_failure" | "failure"
    key_findings: list[str] = []
