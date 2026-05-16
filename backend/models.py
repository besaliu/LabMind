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


class RagQuery(BaseModel):
    query: str
    top_k: int = 5


class RagResult(BaseModel):
    run_id: str
    similarity: float
    summary: str
    instruments: list[str] = []
    status: str = ""
    key_differences: list[str] = []


class FinalizePayload(BaseModel):
    report: str
    outcome: str  # "success" | "partial_failure" | "failure"
    key_findings: list[str] = []
