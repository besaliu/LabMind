from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfileDoc:
    run_id: str
    text: str
    summary: str
    metadata: dict[str, Any]


@dataclass
class SimilarityResult:
    run_id: str
    similarity: float
    summary: str
    instruments: list[str]
    status: str
    key_differences: list[str] = field(default_factory=list)
