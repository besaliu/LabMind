"""End-to-end smoke test against a running docker-compose stack.

Run only when the stack is up:
    docker compose up -d backend vix-temp-controller vix-ph-probe vix-microscopy-imager
    LABMIND_E2E=1 pytest tests/test_e2e_smoke.py -v
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LABMIND_E2E") != "1",
    reason="Set LABMIND_E2E=1 with stack running to enable",
)


def test_instruments_are_registered() -> None:
    # Give instruments a moment after stack-up
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = httpx.get("http://localhost:8000/api/instruments", timeout=2.0)
            registry = r.json() if r.status_code == 200 else {}
            if {"temp_controller_01", "ph_probe_01", "microscopy_imager_01"} <= set(registry):
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("Instruments did not appear in registry within 30s")


def test_phase_transition_changes_temperature_measure() -> None:
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "failure"}, timeout=5.0).raise_for_status()
    time.sleep(1)
    v = httpx.get("http://localhost:8101/measure/temperature", timeout=5.0).json()["value"]
    assert v > 37.5, f"Expected failure-phase temperature > 37.5, got {v}"
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "baseline"}, timeout=5.0).raise_for_status()


def test_status_recovers_after_agent_intervention() -> None:
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "failure"}, timeout=5.0).raise_for_status()
    time.sleep(0.5)
    httpx.post("http://localhost:8101/command/temperature", json={"target_temp_c": 35.0}, timeout=5.0).raise_for_status()
    converged = False
    for _ in range(20):
        time.sleep(0.5)
        v = httpx.get("http://localhost:8101/measure/temperature", timeout=5.0).json()["value"]
        if 34.0 <= v <= 36.0:
            converged = True
            break
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "baseline"}, timeout=5.0)
    assert converged, "Temperature did not converge into the nominal band after set_temperature(35.0)"
