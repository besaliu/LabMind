"""Deterministic field-level diff between a query profile and a retrieved hit.

This is Option A from the design discussion: pure-Python, ~1ms, never
hallucinates. Output is a list of short human-readable strings describing
the meaningful differences, ordered by salience.

The query side arrives as a structured profile string (same template as
stored profiles, per the upload contract). We parse the fields we need
back out with anchored regex against the locked template. If a field
can't be parsed, we fall back to a one-sided descriptive snippet about
the hit so the output is never empty when there's something to say.
"""
from __future__ import annotations

import re
from typing import Any

MAX_DIFFS = 3

# Tolerances — under these deltas, two values are considered "the same".
TEMP_TOL_C = 0.5
COOLING_RATE_TOL = 0.1
DURATION_TOL_HRS = 0.5

_RE_TARGET_TEMP = re.compile(r"target_temp=([\-0-9.]+)C")
_RE_COOLING_RATE = re.compile(r"cooling_rate=([\-0-9.]+)C/hr")
_RE_DURATION = re.compile(r"growth_duration=([\-0-9.]+)h")
_RE_SUBSTRATE = re.compile(r"substrate=([A-Za-z0-9_\-]+)")
_RE_INSTRUMENTS = re.compile(r"^Instruments:\s*(.+)$", re.MULTILINE)
_RE_MICROSCOPY = re.compile(r"^Microscopy observations:\s*(.+)$", re.MULTILINE)


def compute_key_differences(query_text: str, hit_metadata: dict[str, Any], hit_text: str) -> list[str]:
    query = _parse_query(query_text)
    hit = _hit_view(hit_metadata, hit_text)

    diffs: list[str] = []

    # 1. Substrate (highest salience — material change)
    if query.get("substrate") and hit.get("substrate"):
        if query["substrate"] != hit["substrate"]:
            diffs.append(
                f"different substrate ({query['substrate']} vs {hit['substrate']})"
            )
    elif hit.get("substrate") and not query.get("substrate"):
        diffs.append(f"matched run used substrate {hit['substrate']}")

    # 2. Target temperature
    diff = _numeric_delta(query.get("target_temp_c"), hit.get("target_temp_c"), TEMP_TOL_C)
    if diff is not None:
        diffs.append(f"temperature setpoint differs by {abs(diff):.1f}°C")
    elif query.get("target_temp_c") is None and hit.get("target_temp_c"):
        diffs.append(f"matched run targeted {hit['target_temp_c']:.1f}°C")

    # 3. Cooling rate
    diff = _numeric_delta(
        query.get("cooling_rate"), hit.get("cooling_rate"), COOLING_RATE_TOL
    )
    if diff is not None:
        diffs.append(f"cooling rate differs by {abs(diff):.1f}°C/hr")

    # 4. Growth duration
    diff = _numeric_delta(
        query.get("duration_hours"), hit.get("duration_hours"), DURATION_TOL_HRS
    )
    if diff is not None:
        word = "shorter" if diff < 0 else "longer"
        diffs.append(f"{word} growth window")

    # 5. Instruments — symmetric set diff
    q_inst = set(query.get("instruments", []))
    h_inst = set(hit.get("instruments", []))
    if q_inst and h_inst:
        added = h_inst - q_inst
        removed = q_inst - h_inst
        if added:
            diffs.append(f"matched run additionally used {', '.join(sorted(added))}")
        elif removed:
            diffs.append(f"matched run did not use {', '.join(sorted(removed))}")

    # 6. Microscopy labels — symmetric set diff
    q_micro = set(query.get("microscopy", []))
    h_micro = set(hit.get("microscopy", []))
    if h_micro and q_micro and h_micro != q_micro:
        only_hit = h_micro - q_micro
        if only_hit:
            diffs.append(f"matched run observed {', '.join(sorted(only_hit))}")

    return diffs[:MAX_DIFFS]


def _numeric_delta(a: float | None, b: float | None, tol: float) -> float | None:
    """Return signed delta (a - b) if both present AND |delta| > tol, else None."""
    if a is None or b is None:
        return None
    delta = float(a) - float(b)
    if abs(delta) <= tol:
        return None
    return delta


def _parse_query(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not text:
        return out
    if m := _RE_TARGET_TEMP.search(text):
        out["target_temp_c"] = _safe_float(m.group(1))
    if m := _RE_COOLING_RATE.search(text):
        out["cooling_rate"] = _safe_float(m.group(1))
    if m := _RE_DURATION.search(text):
        out["duration_hours"] = _safe_float(m.group(1))
    if m := _RE_SUBSTRATE.search(text):
        out["substrate"] = m.group(1)
    if m := _RE_INSTRUMENTS.search(text):
        out["instruments"] = [p.strip() for p in m.group(1).split(",") if p.strip()]
    if m := _RE_MICROSCOPY.search(text):
        raw = m.group(1).strip()
        out["microscopy"] = [] if raw == "none" else [
            p.strip() for p in raw.split(",") if p.strip()
        ]
    return out


def _hit_view(metadata: dict[str, Any], text: str) -> dict[str, Any]:
    """Build a unified view over a Chroma hit, pulling from metadata where
    structured fields are stored and parsing the text for microscopy labels
    (which we don't store as a flat metadata field)."""
    out: dict[str, Any] = {
        "substrate": metadata.get("substrate") or None,
        "target_temp_c": _safe_float(metadata.get("target_temp_c")),
        "cooling_rate": _safe_float(metadata.get("cooling_rate_c_per_hour")),
        "duration_hours": _safe_float(metadata.get("growth_duration_hours")),
        "instruments": [
            i for i in str(metadata.get("instruments", "")).split("|") if i
        ],
    }
    if m := _RE_MICROSCOPY.search(text or ""):
        raw = m.group(1).strip()
        out["microscopy"] = [] if raw == "none" else [
            p.strip() for p in raw.split(",") if p.strip()
        ]
    else:
        out["microscopy"] = []
    return out


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
