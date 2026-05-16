git fetch origin# VIX Mock Instruments — Implementation Plan (Module 5 / Issue #6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Virtual Instrument Interface (VIX) — three standalone Python HTTP servers (`temp_controller`, `ph_probe`, `microscopy_imager`) that self-register with the FastAPI backend (Issue #3), stream scenario-driven analytics with **threshold-derived status**, respond to control commands that visibly move readings, and can be choreographed through a 3-phase demo arc (baseline → failure → recovery) by `demo_controller.py`.

**Architecture:** A shared `vix/instrument_base.py` owns the FastAPI app, startup self-registration, the periodic analytics-emit loop, the scenario state machine (`baseline | failure | recovery`), threshold-driven status computation, and dispatch tables for `/measure/{metric}` and `/command/{action}`. Scenario noise lives in `vix/scenario.py`; status thresholds live in `vix/status.py`. Each instrument is a thin subclass declaring its registration payload, metric handlers, command handlers, and a small dynamics model so agent commands change subsequent readings. `demo_controller.py` is a CLI that POSTs `/scenario/phase` to each instrument.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, httpx (self-register, demo controller, ASGI test transport), Pillow (synthetic microscopy PNG), pytest + pytest-asyncio.

---

## File Structure

All paths from repo root `C:\Users\natha\OneDrive\Documents\GitHub\LabMind`.

### Files to create

| File | Responsibility |
|---|---|
| `vix/requirements.txt` | Pin VIX-only deps |
| `vix/Dockerfile` | Container image — `CMD` overridden per service in `docker-compose.yml` |
| `vix/__init__.py` | Marks `vix` as importable from tests |
| `vix/scenario.py` | `Scenario` JSON loader + noisy `sample(metric)` per phase |
| `vix/status.py` | `compute_status(readings, thresholds) -> "nominal" \| "warning" \| "critical"` |
| `vix/instrument_base.py` | `InstrumentBase` class: app factory, register, analytics loop (uses `compute_status`), dispatch, phase endpoint |
| `vix/temp_controller.py` | `TempController` (port 8101). Temperature dynamics converge toward `setpoint_override` once a `set_temperature` command lands. |
| `vix/ph_probe.py` | `PhProbe` (port 8102). pH dynamics converge toward `target_ph` once `add_buffer` is called. |
| `vix/microscopy_imager.py` | `MicroscopyImager` (port 8103). `capture_image` (async) renders a phase-dependent PNG and awaits a one-off analytics POST with `image_b64`. |
| `vix/demo_controller.py` | CLI: `python -m vix.demo_controller --phase failure` |
| `vix/scenarios/temp_controller.json` | Per-phase reading distributions + thresholds |
| `vix/scenarios/ph_probe.json` | Per-phase reading distributions + thresholds |
| `vix/scenarios/microscopy_imager.json` | Per-phase reading distributions + thresholds + image generator params |
| `vix/pytest.ini` | Configures `pythonpath = .` so `from vix.* import *` resolves when pytest runs from `vix/` |
| `vix/tests/__init__.py` | Marks tests package |
| `vix/tests/conftest.py` | Mock backend (FastAPI) + httpx `AsyncClient` fixture using ASGI transport |
| `vix/tests/test_scenario.py` | Phase transitions, deterministic sampling, error cases |
| `vix/tests/test_status.py` | `compute_status` rules across all three levels |
| `vix/tests/test_instrument_base.py` | Self-register, analytics loop, 409 handling, dispatch, scenario phase endpoint, async command support |
| `vix/tests/test_temp_controller.py` | Registration payload, measure endpoints, dynamics on `set_temperature`, threshold-derived status |
| `vix/tests/test_ph_probe.py` | Registration payload, measure endpoints, dynamics on `add_buffer`, threshold-derived status |
| `vix/tests/test_microscopy_imager.py` | Registration, measure endpoints, async `capture_image` produces PNG + posts `image_b64` analytics |
| `vix/tests/test_demo_controller.py` | Fans `/scenario/phase` to all instruments |
| `vix/tests/test_e2e_smoke.py` | Opt-in (`LABMIND_E2E=1`) smoke against running stack |

### Files NOT modified

- `instruments/catalog/*.yaml` — VIX must conform to these (already in repo); the plan never edits them.
- `backend/**` — Issue #3 backend is closed and shipped. VIX adapts to it, not the other way around.
- `docker-compose.yml` — already wires `vix-temp-controller`, `vix-ph-probe`, `vix-microscopy-imager` services with `BACKEND_URL`, `VIX_INTERVAL_SECONDS` env and the exact `python {name}.py --port NNNN` commands the plan implements.

---

## Backend contract alignment (Issue #3)

Pulled from `backend/routers/analytics.py`, `backend/routers/instruments.py`, `backend/storage.py`, and the Issue #3 description. VIX must obey these or the existing backend tests (and the live demo) break:

| Concern | Backend behaviour | VIX implication |
|---|---|---|
| `POST /api/instruments/register` body | `{instrument_id, type, name, port, capabilities: [str]}` | Self-register payload uses these exact keys |
| `POST /api/instruments/register` response | `{ok: true, run_id: str \| null}` | Register can be called any time; `run_id=null` is normal pre-experiment |
| `POST /api/analytics` body | `{instrument_id, timestamp, readings: {key: value}, status}` | Analytics payload uses these exact keys |
| No active experiment | `/api/analytics` returns **409** | Analytics loop logs at debug and **keeps emitting** — do not crash, do not back off, the operator will upload + confirm an experiment mid-run |
| Dispatch by type | Backend uses `registry.json[instrument_id].type` (or falls back to `instrument_id` minus `_NN` suffix) | Instrument IDs MUST be `{type}_NN` so dispatch works even before the registry write lands |
| `temp_controller` readings persisted | `temperature_c`, `setpoint_c` (only) | Emit both keys every tick. `cooling_rate_c_per_hour` is silently discarded by the backend; that's fine — the agent reads it via the `read_cooling_rate` MCP tool / `GET /measure/cooling_rate` |
| `ph_probe` / `chemical_stability` readings persisted | `impurity_ppm`, `saturation_pct`, `ph` | Emit all three every tick |
| `microscopy_imager` readings persisted | Only `image_b64` is consumed (base64-encoded PNG → written to `microscope.png`). Other keys ignored | Emit `clarity_pct`/`defect_count` every tick (harmless / ignored); emit `image_b64` only when `capture_image` is called |
| CSV status column | Backend writes whatever VIX sends in `status` | VIX computes status from current readings vs thresholds → "nominal" / "warning" / "critical" |
| `last_seen` | Backend touches `registry[id].last_seen` on every analytics POST | VIX doesn't need to manage this |

---

## Conventions

- **Reading keys (frozen by backend):**
  - `temp_controller`: `temperature_c`, `setpoint_c`, `cooling_rate_c_per_hour`
  - `ph_probe`: `ph`, `saturation_pct`, `impurity_ppm`
  - `microscopy_imager`: `clarity_pct`, `defect_count`, and on capture only `image_b64`
- **Instrument IDs:** `temp_controller_01` (port 8101), `ph_probe_01` (port 8102), `microscopy_imager_01` (port 8103) — match `SCHEMAS.md` and the backend's `_resolve_type` fallback.
- **Timestamps:** `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` → ends in `Z` as `SCHEMAS.md` examples show.
- **Status computation:** `vix/status.py` walks readings, looks up thresholds, returns the **worst** level encountered. Default if no threshold matches → `"nominal"`.
- **Status thresholds:** per-phase-independent, defined once at the top of each scenario JSON. Shape: `{metric_name: {"nominal": [min, max], "warning": [min, max]}}` — anything outside the warning range is critical.
- **Dynamics model (used by `temp_controller` and `ph_probe`):** when a setpoint-style override has been set, the next sample is `state + alpha * (override - state) + small_noise`, with `alpha=0.4` by default. This makes agent intervention visibly converge over ~5 ticks. Tests use `alpha=1.0` for determinism.
- **Async command handlers:** the base class accepts both sync (`Callable[[dict], dict]`) and async (`Callable[[dict], Awaitable[dict]]`) handlers — `microscopy_imager`'s `_capture` is async because it awaits an HTTP POST.
- **SCENARIO env var:** declared by docker-compose but currently unused by VIX. Single hard-coded JSON per instrument is fine for the hackathon; the var is reserved for future multi-scenario support. Code does not read it.
- **Backend 409 handling:** `analytics_loop` logs 409 at debug level, **does not** sleep extra, does not back off. Registration retries every `interval_seconds` until 2xx.

---

## Task 1: VIX package scaffold

**Files:**
- Create: `vix/__init__.py`
- Create: `vix/tests/__init__.py`
- Create: `vix/requirements.txt`
- Create: `vix/Dockerfile`
- Create: `vix/pytest.ini`
- Create: `vix/scenarios/.gitkeep`

- [ ] **Step 1: Create package markers (each file is empty unless noted)**

`vix/__init__.py`:
```python
```

`vix/tests/__init__.py`:
```python
```

`vix/scenarios/.gitkeep`:
```
```

- [ ] **Step 2: Write `vix/requirements.txt`**

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
httpx==0.28.1
Pillow==11.0.0
pytest==8.3.4
pytest-asyncio==0.24.0
anyio==4.7.0
```

- [ ] **Step 3: Write `vix/pytest.ini`**

```ini
[pytest]
pythonpath = ..
asyncio_mode = auto
testpaths = tests
```

`pythonpath = ..` makes `from vix.scenario import Scenario` resolve when pytest runs from `vix/`.

- [ ] **Step 4: Write `vix/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/
# CMD overridden per-service in docker-compose.yml
CMD ["python", "temp_controller.py", "--port", "8101"]
```

`PYTHONPATH=/` lets the script-style `python temp_controller.py` still resolve `from vix.instrument_base import InstrumentBase` when the working dir is `/app`. (Files inside the image live under `/app`, but we set `WORKDIR /app` and reference siblings via `from vix.*`; alternative path setup is to invoke via `python -m vix.temp_controller --port 8101` — but docker-compose already pins the script-style commands and we don't want to fight it.)

To make `from vix.*` work with script-style invocation, the Dockerfile copies the `vix` package under `/app/vix/...`. Verify in Step 5.

Actually we need the simpler approach: `COPY . /app` puts files at `/app/__init__.py`, `/app/temp_controller.py`, etc. (no `vix` subdir inside the container). So inside the container, imports must be flat (`from instrument_base import InstrumentBase`). Pick one approach. **Decision:** restructure imports to use **relative imports** that work both as a script (with `sys.path` adjusted) and as `vix.*` from the host pytest.

Simpler decision: each instrument adds a small `sys.path` fix at the top so `from vix.instrument_base import ...` resolves whether running from `/app` (container) or repo root (tests).

Revise `vix/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /opt
COPY . /opt/vix
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt
WORKDIR /opt/vix
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "temp_controller.py", "--port", "8101"]
```

Now the container has `/opt/vix/temp_controller.py`, `PYTHONPATH=/opt`, so `from vix.instrument_base import InstrumentBase` works. `python temp_controller.py --port 8101` from `/opt/vix` works because the script file is right there. ✓

- [ ] **Step 5: Verify scaffold layout**

Run: `ls vix/`
Expected: `Dockerfile  __init__.py  pytest.ini  requirements.txt  scenarios  tests`

- [ ] **Step 6: Commit**

```bash
git add vix/__init__.py vix/tests/__init__.py vix/requirements.txt vix/Dockerfile vix/pytest.ini vix/scenarios/.gitkeep
git commit -m "feat(vix): scaffold package, Dockerfile, pytest config"
```

---

## Task 2: Scenario loader (`vix/scenario.py`)

Pure noise/phase machinery. No status, no thresholds — those live in `vix/status.py`.

**Files:**
- Create: `vix/scenario.py`
- Test: `vix/tests/test_scenario.py`

- [ ] **Step 1: Write the failing test `vix/tests/test_scenario.py`**

```python
import json
import random
from pathlib import Path

import pytest

from vix.scenario import Scenario


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    spec = {
        "thresholds": {
            "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
        },
        "baseline": {
            "readings": {
                "temperature_c": {"mean": 35.0, "noise": 0.1},
                "setpoint_c":    {"mean": 35.0, "noise": 0.0},
            },
        },
        "failure": {
            "readings": {
                "temperature_c": {"mean": 38.5, "noise": 0.2},
                "setpoint_c":    {"mean": 35.0, "noise": 0.0},
            },
        },
        "recovery": {
            "readings": {
                "temperature_c": {"mean": 35.5, "noise": 0.1},
                "setpoint_c":    {"mean": 34.0, "noise": 0.0},
            },
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    return p


def test_default_phase_is_baseline(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.current_phase == "baseline"


def test_thresholds_loaded(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.thresholds == {
        "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    }


def test_sample_is_near_phase_mean(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    samples = [s.sample("temperature_c") for _ in range(50)]
    assert all(34.5 < x < 35.5 for x in samples)


def test_set_phase_switches_distribution(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    s.set_phase("failure")
    assert s.current_phase == "failure"
    samples = [s.sample("temperature_c") for _ in range(50)]
    assert all(38.0 < x < 39.0 for x in samples)


def test_zero_noise_is_exact(spec_file: Path) -> None:
    s = Scenario(spec_file, rng=random.Random(0))
    assert s.sample("setpoint_c") == 35.0


def test_unknown_phase_raises(spec_file: Path) -> None:
    s = Scenario(spec_file)
    with pytest.raises(ValueError):
        s.set_phase("explode")


def test_unknown_metric_raises(spec_file: Path) -> None:
    s = Scenario(spec_file)
    with pytest.raises(KeyError):
        s.sample("not_a_metric")


def test_missing_baseline_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"failure": {"readings": {}}}))
    with pytest.raises(ValueError):
        Scenario(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_scenario.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.scenario'`

- [ ] **Step 3: Implement `vix/scenario.py`**

```python
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


class Scenario:
    """Phase-based reading generator loaded from a JSON spec file.

    Spec shape:
        {
            "thresholds": { metric: {"nominal": [lo, hi], "warning": [lo, hi]} },
            "<phase>":    { "readings": { metric: {"mean": float, "noise": float} } },
            ...
        }
    """

    def __init__(self, spec_path: Path | str, rng: random.Random | None = None) -> None:
        self._spec: dict[str, Any] = json.loads(Path(spec_path).read_text())
        if "baseline" not in self._spec:
            raise ValueError(f"Scenario {spec_path} is missing required 'baseline' phase")
        self._rng = rng or random.Random()
        self._phase: str = "baseline"
        self.thresholds: dict[str, Any] = self._spec.get("thresholds", {})

    @property
    def current_phase(self) -> str:
        return self._phase

    def set_phase(self, phase: str) -> None:
        if phase not in self._spec or phase == "thresholds":
            raise ValueError(f"Unknown phase {phase!r}")
        self._phase = phase

    def sample(self, metric: str) -> float:
        readings = self._spec[self._phase]["readings"]
        if metric not in readings:
            raise KeyError(f"Metric {metric!r} not defined for phase {self._phase!r}")
        spec = readings[metric]
        mean = float(spec["mean"])
        noise = float(spec.get("noise", 0.0))
        if noise == 0.0:
            return mean
        return mean + self._rng.uniform(-noise, noise)

    def phase_spec(self, phase: str | None = None) -> dict[str, Any]:
        """Return the raw phase block — used by subclasses (e.g. imager) for non-reading data."""
        return self._spec[phase or self._phase]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_scenario.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add vix/scenario.py vix/tests/test_scenario.py
git commit -m "feat(vix): scenario loader with phase transitions and threshold metadata"
```

---

## Task 3: Status helper (`vix/status.py`)

Pure function. `compute_status(readings, thresholds)` returns `"nominal" | "warning" | "critical"`. Worst-of-all-metrics wins.

**Files:**
- Create: `vix/status.py`
- Test: `vix/tests/test_status.py`

- [ ] **Step 1: Write the failing test `vix/tests/test_status.py`**

```python
import pytest

from vix.status import compute_status

T = {
    "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    "ph":            {"nominal": [6.8, 7.4],   "warning": [6.5, 7.6]},
}


def test_nominal_when_all_inside_nominal() -> None:
    assert compute_status({"temperature_c": 35.0, "ph": 7.0}, T) == "nominal"


def test_warning_when_one_metric_in_warning_band() -> None:
    assert compute_status({"temperature_c": 36.5, "ph": 7.0}, T) == "warning"


def test_critical_when_one_metric_outside_warning() -> None:
    assert compute_status({"temperature_c": 38.5, "ph": 7.0}, T) == "critical"


def test_critical_below_warning_band() -> None:
    assert compute_status({"temperature_c": 30.0, "ph": 7.0}, T) == "critical"


def test_worst_metric_wins() -> None:
    # ph is critical, temperature only warning → critical
    assert compute_status({"temperature_c": 36.5, "ph": 5.0}, T) == "critical"


def test_unknown_metrics_ignored() -> None:
    assert compute_status({"random_metric": 9999, "temperature_c": 35.0}, T) == "nominal"


def test_empty_readings_is_nominal() -> None:
    assert compute_status({}, T) == "nominal"


def test_inclusive_bounds_on_nominal() -> None:
    assert compute_status({"temperature_c": 34.0}, T) == "nominal"
    assert compute_status({"temperature_c": 36.0}, T) == "nominal"


def test_inclusive_bounds_on_warning() -> None:
    assert compute_status({"temperature_c": 33.0}, T) == "warning"
    assert compute_status({"temperature_c": 37.0}, T) == "warning"


def test_non_numeric_reading_ignored() -> None:
    # e.g. base64 image strings — must not blow up
    assert compute_status({"image_b64": "AAAA", "temperature_c": 35.0}, T) == "nominal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.status'`

- [ ] **Step 3: Implement `vix/status.py`**

```python
from __future__ import annotations

from typing import Any

Status = str  # "nominal" | "warning" | "critical"

_RANK = {"nominal": 0, "warning": 1, "critical": 2}


def compute_status(readings: dict[str, Any], thresholds: dict[str, dict[str, list[float]]]) -> Status:
    """Return the worst status implied by the current readings.

    Thresholds shape per metric: {"nominal": [lo, hi], "warning": [lo, hi]}.
    Bounds are inclusive. Anything outside the warning band is "critical".
    Metrics not in `thresholds` or non-numeric values are ignored.
    """
    worst: Status = "nominal"
    for metric, value in readings.items():
        if metric not in thresholds:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        spec = thresholds[metric]
        nom_lo, nom_hi = spec["nominal"]
        warn_lo, warn_hi = spec["warning"]
        if nom_lo <= value <= nom_hi:
            level: Status = "nominal"
        elif warn_lo <= value <= warn_hi:
            level = "warning"
        else:
            level = "critical"
        if _RANK[level] > _RANK[worst]:
            worst = level
    return worst
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_status.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add vix/status.py vix/tests/test_status.py
git commit -m "feat(vix): threshold-derived status helper"
```

---

## Task 4: `InstrumentBase` (`vix/instrument_base.py`)

Owns the FastAPI app, lifecycle, dispatch. Status now comes from `compute_status(build_readings(), scenario.thresholds)`. Async-aware command dispatch.

**Files:**
- Create: `vix/instrument_base.py`
- Test: `vix/tests/conftest.py`
- Test: `vix/tests/test_instrument_base.py`

- [ ] **Step 1: Write `vix/tests/conftest.py`**

```python
from __future__ import annotations

from typing import Any

import httpx
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request


class MockBackend:
    """FastAPI app that captures register/analytics calls and can return 409 for analytics."""

    def __init__(self) -> None:
        self.registrations: list[dict[str, Any]] = []
        self.analytics: list[dict[str, Any]] = []
        self.reject_analytics: bool = False
        self.app = FastAPI()

        @self.app.post("/api/instruments/register")
        async def register(req: Request) -> dict[str, Any]:
            self.registrations.append(await req.json())
            return {"ok": True, "run_id": None}

        @self.app.post("/api/analytics")
        async def analytics(req: Request) -> dict[str, Any]:
            payload = await req.json()
            if self.reject_analytics:
                raise HTTPException(409, "No active experiment")
            self.analytics.append(payload)
            return {"ok": True}


@pytest_asyncio.fixture
async def mock_backend() -> MockBackend:
    return MockBackend()


@pytest_asyncio.fixture
async def backend_client(mock_backend: MockBackend):
    transport = httpx.ASGITransport(app=mock_backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend") as c:
        yield c
```

- [ ] **Step 2: Write the failing test `vix/tests/test_instrument_base.py`**

```python
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import httpx
import pytest

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario


def _spec(tmp_path: Path) -> Path:
    spec = {
        "thresholds": {"value": {"nominal": [0.0, 2.0], "warning": [-1.0, 8.0]}},
        "baseline": {"readings": {"value": {"mean": 1.0, "noise": 0.0}}},
        "failure":  {"readings": {"value": {"mean": 9.0, "noise": 0.0}}},
    }
    p = tmp_path / "dummy.json"
    p.write_text(json.dumps(spec))
    return p


class DummyInstrument(InstrumentBase):
    instrument_type = "dummy"
    instrument_id = "dummy_01"
    name = "Dummy"
    capabilities = ["read_value", "set_value"]

    def __init__(self, scenario: Scenario, **kw):
        super().__init__(scenario=scenario, **kw)
        self.last_set: float | None = None
        self.register_measure("value", lambda: {
            "value": self.scenario.sample("value"), "unit": "x", "timestamp": self._now(),
        })
        self.register_command("value", self._set_value)

    def _set_value(self, body: dict) -> dict:
        self.last_set = float(body["value"])
        return {"ok": True, "new_value": self.last_set}

    def build_readings(self) -> dict:
        return {"value": self.scenario.sample("value")}


@pytest.mark.asyncio
async def test_health(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "instrument_id": "dummy_01"}


@pytest.mark.asyncio
async def test_self_registers_on_startup(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "dummy_01"
    assert reg["type"] == "dummy"
    assert reg["port"] == 9999
    assert reg["capabilities"] == ["read_value", "set_value"]


@pytest.mark.asyncio
async def test_analytics_loop_emits_on_interval_with_status(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.18)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(mock_backend.analytics) >= 2
    p = mock_backend.analytics[0]
    assert p["instrument_id"] == "dummy_01"
    assert p["readings"]["value"] == 1.0
    assert p["status"] == "nominal"  # value=1.0 is inside [0,2]
    assert p["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_analytics_loop_status_reflects_phase(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    inst.scenario.set_phase("failure")  # value=9.0, outside warning [-1,8] → critical
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.12)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert mock_backend.analytics[0]["status"] == "critical"


@pytest.mark.asyncio
async def test_analytics_loop_survives_409(tmp_path, backend_client, mock_backend) -> None:
    mock_backend.reject_analytics = True
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.12)
    # Now let it through
    mock_backend.reject_analytics = False
    await asyncio.sleep(0.12)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # At least one analytics POST eventually succeeds — loop did not crash
    assert len(mock_backend.analytics) >= 1


@pytest.mark.asyncio
async def test_measure_endpoint(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.get("/measure/value")
        assert r.status_code == 200
        assert r.json()["value"] == 1.0


@pytest.mark.asyncio
async def test_unknown_measure_404(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        assert (await c.get("/measure/nope")).status_code == 404


@pytest.mark.asyncio
async def test_command_endpoint_dispatches_sync(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/value", json={"value": 7.5})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "new_value": 7.5}
        assert inst.last_set == 7.5


@pytest.mark.asyncio
async def test_command_endpoint_dispatches_async(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)

    async def async_handler(body: dict) -> dict:
        await asyncio.sleep(0)
        return {"ok": True, "asynced": True, "value": body.get("v")}

    inst.register_command("async_action", async_handler)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/async_action", json={"v": 3})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "asynced": True, "value": 3}


@pytest.mark.asyncio
async def test_scenario_phase_endpoint(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/scenario/phase", json={"phase": "failure"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "phase": "failure"}
        m = (await c.get("/measure/value")).json()
        assert m["value"] == 9.0


@pytest.mark.asyncio
async def test_scenario_phase_unknown_400(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/scenario/phase", json={"phase": "explode"})
        assert r.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_instrument_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.instrument_base'`

- [ ] **Step 4: Implement `vix/instrument_base.py`**

```python
from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

import httpx
from fastapi import FastAPI, HTTPException, Request

from vix.scenario import Scenario
from vix.status import compute_status

logger = logging.getLogger(__name__)

MeasureHandler = Callable[[], dict[str, Any]]
CommandHandler = Union[Callable[[dict[str, Any]], dict[str, Any]],
                       Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]]


class InstrumentBase:
    """Common behaviour for every VIX mock instrument."""

    instrument_type: str = ""
    instrument_id: str = ""
    name: str = ""
    capabilities: list[str] = []

    def __init__(
        self,
        scenario: Scenario,
        port: int,
        backend_client: httpx.AsyncClient,
        interval_seconds: float = 30.0,
    ) -> None:
        if not (self.instrument_type and self.instrument_id and self.name):
            raise ValueError("Subclass must set instrument_type/instrument_id/name")
        self.scenario = scenario
        self.port = port
        self._client = backend_client
        self._interval = interval_seconds
        self._measure_handlers: dict[str, MeasureHandler] = {}
        self._command_handlers: dict[str, CommandHandler] = {}
        self.app = self._build_app()

    def register_measure(self, metric: str, handler: MeasureHandler) -> None:
        self._measure_handlers[metric] = handler

    def register_command(self, action: str, handler: CommandHandler) -> None:
        self._command_handlers[action] = handler

    def build_readings(self) -> dict[str, Any]:
        raise NotImplementedError

    async def register(self) -> None:
        payload = {
            "instrument_id": self.instrument_id,
            "type": self.instrument_type,
            "name": self.name,
            "port": self.port,
            "capabilities": list(self.capabilities),
        }
        while True:
            try:
                r = await self._client.post("/api/instruments/register", json=payload, timeout=5.0)
                if r.status_code < 300:
                    logger.info("Registered %s with backend", self.instrument_id)
                    return
                logger.warning("Register returned %s; retrying in %ss", r.status_code, self._interval)
            except httpx.HTTPError as e:
                logger.warning("Register failed: %s; retrying in %ss", e, self._interval)
            await asyncio.sleep(self._interval)

    async def analytics_loop(self) -> None:
        while True:
            try:
                readings = self.build_readings()
                payload = {
                    "instrument_id": self.instrument_id,
                    "timestamp": self._now(),
                    "readings": readings,
                    "status": compute_status(readings, self.scenario.thresholds),
                }
                r = await self._client.post("/api/analytics", json=payload, timeout=5.0)
                if r.status_code == 409:
                    logger.debug("Analytics 409 (no active experiment) — keep streaming")
                elif r.status_code >= 300:
                    logger.warning("Analytics POST returned %s", r.status_code)
            except httpx.HTTPError as e:
                logger.warning("Analytics POST failed: %s", e)
            except Exception as e:  # never let a bad reading take the loop down
                logger.exception("Unexpected error in analytics loop: %s", e)
            await asyncio.sleep(self._interval)

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "instrument_id": self.instrument_id}

        @app.get("/measure/{metric}")
        def measure(metric: str) -> dict[str, Any]:
            handler = self._measure_handlers.get(metric)
            if handler is None:
                raise HTTPException(404, f"Unknown metric {metric!r}")
            return handler()

        @app.post("/command/{action}")
        async def command(action: str, request: Request) -> dict[str, Any]:
            handler = self._command_handlers.get(action)
            if handler is None:
                raise HTTPException(404, f"Unknown command {action!r}")
            body = await request.json() if await request.body() else {}
            result = handler(body)
            if inspect.isawaitable(result):
                result = await result
            return result

        @app.post("/scenario/phase")
        async def scenario_phase(request: Request) -> dict[str, Any]:
            body = await request.json()
            phase = body.get("phase")
            try:
                self.scenario.set_phase(phase)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "phase": phase}

        return app

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_instrument_base.py -v`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add vix/instrument_base.py vix/tests/conftest.py vix/tests/test_instrument_base.py
git commit -m "feat(vix): InstrumentBase with threshold-derived status, async dispatch, 409-resilient loop"
```

---

## Task 5: `temp_controller` with temperature dynamics

Readings emitted: `{temperature_c, setpoint_c, cooling_rate_c_per_hour}`. Commands: `temperature` → sets setpoint override; `cooling_rate` → sets cooling rate override. Once `_setpoint_override` is set, the next `temperature_c` sample uses a dynamics step: `state += alpha * (override - state) + noise`. Tests use `alpha=1.0` to snap deterministically.

**Files:**
- Create: `vix/scenarios/temp_controller.json`
- Create: `vix/temp_controller.py`
- Test: `vix/tests/test_temp_controller.py`

- [ ] **Step 1: Write `vix/scenarios/temp_controller.json`**

```json
{
  "thresholds": {
    "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    "setpoint_c":    {"nominal": [32.0, 38.0], "warning": [30.0, 40.0]}
  },
  "baseline": {
    "readings": {
      "temperature_c": {"mean": 35.0, "noise": 0.1},
      "setpoint_c":    {"mean": 35.0, "noise": 0.0},
      "cooling_rate_c_per_hour": {"mean": 0.5, "noise": 0.0}
    }
  },
  "failure": {
    "readings": {
      "temperature_c": {"mean": 38.5, "noise": 0.3},
      "setpoint_c":    {"mean": 35.0, "noise": 0.0},
      "cooling_rate_c_per_hour": {"mean": 0.1, "noise": 0.05}
    }
  },
  "recovery": {
    "readings": {
      "temperature_c": {"mean": 35.3, "noise": 0.15},
      "setpoint_c":    {"mean": 34.0, "noise": 0.0},
      "cooling_rate_c_per_hour": {"mean": 0.8, "noise": 0.05}
    }
  }
}
```

- [ ] **Step 2: Write the failing test `vix/tests/test_temp_controller.py`**

```python
from __future__ import annotations

import random
from pathlib import Path

import httpx
import pytest

from vix.scenario import Scenario
from vix.temp_controller import TempController

SPEC = Path("../scenarios/temp_controller.json")  # tests run from vix/


def _make(backend_client, alpha=1.0):
    return TempController(
        scenario=Scenario(Path("scenarios/temp_controller.json"), rng=random.Random(0)),
        port=8101,
        backend_client=backend_client,
        interval_seconds=0.05,
        dynamics_alpha=alpha,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "temp_controller_01"
    assert reg["type"] == "temp_controller"
    assert reg["port"] == 8101
    for cap in ("read_temperature", "set_temperature", "read_cooling_rate", "set_cooling_rate"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_temperature_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/temperature")).json()
        assert body["unit"] == "C"
        assert 34.8 < body["value"] < 35.2


@pytest.mark.asyncio
async def test_build_readings_has_required_keys(backend_client) -> None:
    inst = _make(backend_client)
    readings = inst.build_readings()
    assert {"temperature_c", "setpoint_c", "cooling_rate_c_per_hour"} <= set(readings)


@pytest.mark.asyncio
async def test_set_temperature_changes_setpoint_immediately(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/temperature", json={"target_temp_c": 34.0})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "new_value": 34.0}
        readings = inst.build_readings()
        assert readings["setpoint_c"] == 34.0


@pytest.mark.asyncio
async def test_intervention_converges_temperature_under_failure(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    inst.scenario.set_phase("failure")
    # Failure mean = 38.5
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        # Before intervention: critical
        r1 = inst.build_readings()
        from vix.status import compute_status
        assert compute_status(r1, inst.scenario.thresholds) == "critical"

        # Agent intervenes
        await c.post("/command/temperature", json={"target_temp_c": 35.0})
        # With alpha=1.0, one step snaps state to 35.0 (± noise)
        r2 = inst.build_readings()
        assert 34.7 <= r2["temperature_c"] <= 35.3
        assert compute_status(r2, inst.scenario.thresholds) == "nominal"


@pytest.mark.asyncio
async def test_set_cooling_rate_command(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/cooling_rate", json={"rate_c_per_hour": 1.5})
        assert r.status_code == 200
        readings = inst.build_readings()
        assert readings["cooling_rate_c_per_hour"] == 1.5
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_temp_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.temp_controller'`

- [ ] **Step 4: Implement `vix/temp_controller.py`**

```python
from __future__ import annotations

import argparse
import asyncio
import os
import random
from pathlib import Path

import httpx
import uvicorn

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario

SCENARIO_DIR = Path(__file__).parent / "scenarios"


class TempController(InstrumentBase):
    instrument_type = "temp_controller"
    instrument_id = "temp_controller_01"
    name = "Crystal Growth Temperature Controller"
    capabilities = [
        "read_temperature",
        "set_temperature",
        "read_cooling_rate",
        "set_cooling_rate",
    ]

    def __init__(self, scenario: Scenario, dynamics_alpha: float = 0.4, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._setpoint_override: float | None = None
        self._cooling_rate_override: float | None = None
        self._temp_state: float | None = None
        self._alpha = dynamics_alpha
        self._rng = random.Random()

        self.register_measure("temperature", lambda: {
            "value": self._next_temperature(), "unit": "C", "timestamp": self._now(),
        })
        self.register_measure("setpoint", lambda: {
            "value": self._setpoint(), "unit": "C", "timestamp": self._now(),
        })
        self.register_measure("cooling_rate", lambda: {
            "value": self._cooling_rate(), "unit": "C/h", "timestamp": self._now(),
        })
        self.register_command("temperature", self._set_temperature)
        self.register_command("cooling_rate", self._set_cooling_rate)

    def _setpoint(self) -> float:
        if self._setpoint_override is not None:
            return self._setpoint_override
        return self.scenario.sample("setpoint_c")

    def _cooling_rate(self) -> float:
        if self._cooling_rate_override is not None:
            return self._cooling_rate_override
        return self.scenario.sample("cooling_rate_c_per_hour")

    def _next_temperature(self) -> float:
        sample = self.scenario.sample("temperature_c")
        if self._setpoint_override is None:
            self._temp_state = sample
            return sample
        # Dynamics: state += alpha * (override - state) + small noise
        if self._temp_state is None:
            self._temp_state = sample
        target = self._setpoint_override
        self._temp_state = self._temp_state + self._alpha * (target - self._temp_state)
        return self._temp_state

    def _set_temperature(self, body: dict) -> dict:
        v = float(body["target_temp_c"])
        self._setpoint_override = v
        return {"ok": True, "new_value": v}

    def _set_cooling_rate(self, body: dict) -> dict:
        v = float(body["rate_c_per_hour"])
        self._cooling_rate_override = v
        return {"ok": True, "new_value": v}

    def build_readings(self) -> dict:
        return {
            "temperature_c": self._next_temperature(),
            "setpoint_c": self._setpoint(),
            "cooling_rate_c_per_hour": self._cooling_rate(),
        }


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "30"))
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = TempController(
            scenario=Scenario(SCENARIO_DIR / "temp_controller.json"),
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        @inst.app.on_event("startup")
        async def _startup() -> None:
            asyncio.create_task(inst.register())
            asyncio.create_task(inst.analytics_loop())

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8101)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_temp_controller.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add vix/temp_controller.py vix/scenarios/temp_controller.json vix/tests/test_temp_controller.py
git commit -m "feat(vix): temp_controller with setpoint dynamics and threshold-derived status"
```

---

## Task 6: `ph_probe` with pH dynamics

Readings: `{ph, saturation_pct, impurity_ppm}`. Command `add_buffer(target_ph, volume_ml)` sets a pH override; subsequent `ph` readings converge toward target with the same `alpha` dynamics. `impurity_ppm` and `saturation_pct` follow the scenario phase only (no command moves them — for the demo, fixing pH is the agent's lever).

**Files:**
- Create: `vix/scenarios/ph_probe.json`
- Create: `vix/ph_probe.py`
- Test: `vix/tests/test_ph_probe.py`

- [ ] **Step 1: Write `vix/scenarios/ph_probe.json`**

```json
{
  "thresholds": {
    "ph":             {"nominal": [6.8, 7.4], "warning": [6.5, 7.6]},
    "saturation_pct": {"nominal": [75.0, 80.0], "warning": [70.0, 85.0]},
    "impurity_ppm":   {"nominal": [0.0, 30.0], "warning": [0.0, 50.0]}
  },
  "baseline": {
    "readings": {
      "ph":             {"mean": 7.1, "noise": 0.05},
      "saturation_pct": {"mean": 78.0, "noise": 1.0},
      "impurity_ppm":   {"mean": 15.0, "noise": 2.0}
    }
  },
  "failure": {
    "readings": {
      "ph":             {"mean": 6.2, "noise": 0.1},
      "saturation_pct": {"mean": 82.0, "noise": 1.5},
      "impurity_ppm":   {"mean": 65.0, "noise": 5.0}
    }
  },
  "recovery": {
    "readings": {
      "ph":             {"mean": 6.95, "noise": 0.05},
      "saturation_pct": {"mean": 79.0, "noise": 1.0},
      "impurity_ppm":   {"mean": 28.0, "noise": 3.0}
    }
  }
}
```

- [ ] **Step 2: Write the failing test `vix/tests/test_ph_probe.py`**

```python
from __future__ import annotations

import random
from pathlib import Path

import httpx
import pytest

from vix.ph_probe import PhProbe
from vix.scenario import Scenario
from vix.status import compute_status


def _make(backend_client, alpha=1.0):
    return PhProbe(
        scenario=Scenario(Path("scenarios/ph_probe.json"), rng=random.Random(0)),
        port=8102,
        backend_client=backend_client,
        interval_seconds=0.05,
        dynamics_alpha=alpha,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "ph_probe_01"
    assert reg["type"] == "ph_probe"
    assert reg["port"] == 8102
    for cap in ("read_ph", "read_saturation", "add_buffer"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_ph_baseline_range(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/ph")).json()
        assert 7.0 < body["value"] < 7.2


@pytest.mark.asyncio
async def test_build_readings_keys(backend_client) -> None:
    inst = _make(backend_client)
    assert set(inst.build_readings()) == {"ph", "saturation_pct", "impurity_ppm"}


@pytest.mark.asyncio
async def test_status_critical_under_failure_phase(backend_client) -> None:
    inst = _make(backend_client)
    inst.scenario.set_phase("failure")
    r = inst.build_readings()
    assert compute_status(r, inst.scenario.thresholds) == "critical"


@pytest.mark.asyncio
async def test_add_buffer_drives_ph_toward_target(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    inst.scenario.set_phase("failure")
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/buffer", json={"target_ph": 7.0, "volume_ml": 5.0})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["new_value"] == 7.0
        ph = inst.build_readings()["ph"]
        assert abs(ph - 7.0) < 0.15  # snapped with alpha=1.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_ph_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.ph_probe'`

- [ ] **Step 4: Implement `vix/ph_probe.py`**

```python
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx
import uvicorn

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario

SCENARIO_DIR = Path(__file__).parent / "scenarios"


class PhProbe(InstrumentBase):
    instrument_type = "ph_probe"
    instrument_id = "ph_probe_01"
    name = "Solution pH and Saturation Probe"
    capabilities = ["read_ph", "read_saturation", "add_buffer"]

    def __init__(self, scenario: Scenario, dynamics_alpha: float = 0.4, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._ph_override: float | None = None
        self._ph_state: float | None = None
        self._alpha = dynamics_alpha

        self.register_measure("ph", lambda: {
            "value": self._next_ph(), "unit": "pH", "timestamp": self._now(),
        })
        self.register_measure("saturation", lambda: {
            "value": self.scenario.sample("saturation_pct"), "unit": "%", "timestamp": self._now(),
        })
        self.register_command("buffer", self._add_buffer)

    def _next_ph(self) -> float:
        sample = self.scenario.sample("ph")
        if self._ph_override is None:
            self._ph_state = sample
            return sample
        if self._ph_state is None:
            self._ph_state = sample
        self._ph_state = self._ph_state + self._alpha * (self._ph_override - self._ph_state)
        return self._ph_state

    def _add_buffer(self, body: dict) -> dict:
        target = float(body["target_ph"])
        _ = float(body.get("volume_ml", 0.0))
        self._ph_override = target
        return {"ok": True, "new_value": target}

    def build_readings(self) -> dict:
        return {
            "ph": self._next_ph(),
            "saturation_pct": self.scenario.sample("saturation_pct"),
            "impurity_ppm": self.scenario.sample("impurity_ppm"),
        }


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "30"))
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = PhProbe(
            scenario=Scenario(SCENARIO_DIR / "ph_probe.json"),
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        @inst.app.on_event("startup")
        async def _startup() -> None:
            asyncio.create_task(inst.register())
            asyncio.create_task(inst.analytics_loop())

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_ph_probe.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add vix/ph_probe.py vix/scenarios/ph_probe.json vix/tests/test_ph_probe.py
git commit -m "feat(vix): ph_probe with add_buffer dynamics and threshold-derived status"
```

---

## Task 7: `microscopy_imager` with async capture

Readings on every tick: `{clarity_pct, defect_count}` (no image — backend ignores anything without `image_b64`). `capture_image` is async: renders a phase-dependent PNG via Pillow, awaits a one-off `POST /api/analytics` with `image_b64` set so the backend writes `microscope.png`, then returns `{ok, image_b64}` to the caller.

**Files:**
- Create: `vix/scenarios/microscopy_imager.json`
- Create: `vix/microscopy_imager.py`
- Test: `vix/tests/test_microscopy_imager.py`

- [ ] **Step 1: Write `vix/scenarios/microscopy_imager.json`**

```json
{
  "thresholds": {
    "clarity_pct":  {"nominal": [85.0, 100.0], "warning": [70.0, 100.0]},
    "defect_count": {"nominal": [0.0, 3.0], "warning": [0.0, 8.0]}
  },
  "baseline": {
    "readings": {
      "clarity_pct":  {"mean": 92.0, "noise": 1.0},
      "defect_count": {"mean": 1.0,  "noise": 0.5}
    },
    "image": {"base_color": [200, 220, 255], "noise_amp": 5, "defect_blobs": 0}
  },
  "failure": {
    "readings": {
      "clarity_pct":  {"mean": 62.0, "noise": 3.0},
      "defect_count": {"mean": 14.0, "noise": 2.0}
    },
    "image": {"base_color": [200, 180, 180], "noise_amp": 35, "defect_blobs": 12}
  },
  "recovery": {
    "readings": {
      "clarity_pct":  {"mean": 86.0, "noise": 1.5},
      "defect_count": {"mean": 3.0,  "noise": 1.0}
    },
    "image": {"base_color": [205, 210, 235], "noise_amp": 12, "defect_blobs": 3}
  }
}
```

- [ ] **Step 2: Write the failing test `vix/tests/test_microscopy_imager.py`**

```python
from __future__ import annotations

import base64
import random
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from vix.microscopy_imager import MicroscopyImager
from vix.scenario import Scenario
from vix.status import compute_status


def _make(backend_client):
    return MicroscopyImager(
        scenario=Scenario(Path("scenarios/microscopy_imager.json"), rng=random.Random(0)),
        port=8103,
        backend_client=backend_client,
        interval_seconds=0.05,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "microscopy_imager_01"
    assert reg["type"] == "microscopy_imager"
    assert reg["port"] == 8103
    for cap in ("capture_image", "read_clarity_score", "read_defect_classification"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_clarity_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/clarity")).json()
        assert 90.0 < body["value"] < 94.0


@pytest.mark.asyncio
async def test_measure_defects_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/defects")).json()
        assert 0 <= body["value"] <= 2


@pytest.mark.asyncio
async def test_build_readings_excludes_image(backend_client) -> None:
    inst = _make(backend_client)
    r = inst.build_readings()
    assert set(r) == {"clarity_pct", "defect_count"}
    assert "image_b64" not in r


@pytest.mark.asyncio
async def test_status_critical_during_failure(backend_client) -> None:
    inst = _make(backend_client)
    inst.scenario.set_phase("failure")
    r = inst.build_readings()
    assert compute_status(r, inst.scenario.thresholds) == "critical"


@pytest.mark.asyncio
async def test_capture_image_posts_b64_analytics(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/capture", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        img = Image.open(BytesIO(base64.b64decode(body["image_b64"])))
        assert img.format == "PNG"
    img_posts = [p for p in mock_backend.analytics if "image_b64" in p["readings"]]
    assert len(img_posts) == 1
    assert img_posts[0]["instrument_id"] == "microscopy_imager_01"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd vix && pytest tests/test_microscopy_imager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.microscopy_imager'`

- [ ] **Step 4: Implement `vix/microscopy_imager.py`**

```python
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import random
from io import BytesIO
from pathlib import Path

import httpx
import uvicorn
from PIL import Image, ImageDraw

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario
from vix.status import compute_status

SCENARIO_DIR = Path(__file__).parent / "scenarios"
IMAGE_SIZE = (256, 256)


class MicroscopyImager(InstrumentBase):
    instrument_type = "microscopy_imager"
    instrument_id = "microscopy_imager_01"
    name = "Crystal Microscopy Imager"
    capabilities = ["capture_image", "read_clarity_score", "read_defect_classification"]

    def __init__(self, scenario: Scenario, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._rng = random.Random(0)

        self.register_measure("clarity", lambda: {
            "value": self.scenario.sample("clarity_pct"), "unit": "%", "timestamp": self._now(),
        })
        self.register_measure("defects", lambda: {
            "value": int(round(self.scenario.sample("defect_count"))),
            "unit": "count", "timestamp": self._now(),
        })
        self.register_command("capture", self._capture)

    def build_readings(self) -> dict:
        return {
            "clarity_pct": self.scenario.sample("clarity_pct"),
            "defect_count": int(round(self.scenario.sample("defect_count"))),
        }

    async def _capture(self, body: dict) -> dict:
        b64 = self._render_image_b64()
        payload = {
            "instrument_id": self.instrument_id,
            "timestamp": self._now(),
            "readings": {"image_b64": b64},
            "status": compute_status(self.build_readings(), self.scenario.thresholds),
        }
        try:
            await self._client.post("/api/analytics", json=payload, timeout=5.0)
        except httpx.HTTPError:
            pass  # capture still returns the image even if backend is unreachable
        return {"ok": True, "image_b64": b64}

    def _render_image_b64(self) -> str:
        spec = self.scenario.phase_spec()["image"]
        base_color = tuple(spec["base_color"])
        noise_amp = int(spec["noise_amp"])
        defect_blobs = int(spec["defect_blobs"])

        img = Image.new("RGB", IMAGE_SIZE, base_color)
        px = img.load()
        for x in range(IMAGE_SIZE[0]):
            for y in range(IMAGE_SIZE[1]):
                r, g, b = px[x, y]
                jitter = self._rng.randint(-noise_amp, noise_amp)
                px[x, y] = (
                    max(0, min(255, r + jitter)),
                    max(0, min(255, g + jitter)),
                    max(0, min(255, b + jitter)),
                )

        draw = ImageDraw.Draw(img)
        for _ in range(defect_blobs):
            cx = self._rng.randint(0, IMAGE_SIZE[0] - 1)
            cy = self._rng.randint(0, IMAGE_SIZE[1] - 1)
            r = self._rng.randint(4, 12)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(180, 30, 30))

        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "60"))
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = MicroscopyImager(
            scenario=Scenario(SCENARIO_DIR / "microscopy_imager.json"),
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        @inst.app.on_event("startup")
        async def _startup() -> None:
            asyncio.create_task(inst.register())
            asyncio.create_task(inst.analytics_loop())

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd vix && pytest tests/test_microscopy_imager.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add vix/microscopy_imager.py vix/scenarios/microscopy_imager.json vix/tests/test_microscopy_imager.py
git commit -m "feat(vix): microscopy_imager with async capture_image and threshold-derived status"
```

---

## Task 8: `demo_controller.py`

A CLI that fans out `POST /scenario/phase` to all three instruments. One command advances the whole demo arc.

**Files:**
- Create: `vix/demo_controller.py`
- Test: `vix/tests/test_demo_controller.py`

- [ ] **Step 1: Write the failing test `vix/tests/test_demo_controller.py`**

```python
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from vix.demo_controller import drive_phase


@pytest.mark.asyncio
async def test_drive_phase_posts_to_each_instrument() -> None:
    captured: list[tuple[str, dict]] = []

    def make_app(label: str) -> FastAPI:
        app = FastAPI()

        @app.post("/scenario/phase")
        async def hit(req: Request) -> dict:
            payload = await req.json()
            captured.append((label, payload))
            return {"ok": True, "phase": payload.get("phase")}

        return app

    clients = {
        "temp": httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("temp")), base_url="http://temp"),
        "ph":   httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("ph")),   base_url="http://ph"),
        "img":  httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("img")),  base_url="http://img"),
    }
    try:
        results = await drive_phase("failure", list(clients.values()))
    finally:
        for c in clients.values():
            await c.aclose()
    assert len(results) == 3
    assert all(r["ok"] for r in results)
    assert {label for label, _ in captured} == {"temp", "ph", "img"}
    assert all(body == {"phase": "failure"} for _, body in captured)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd vix && pytest tests/test_demo_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vix.demo_controller'`

- [ ] **Step 3: Implement `vix/demo_controller.py`**

```python
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Iterable

import httpx

DEFAULT_INSTRUMENT_URLS = [
    "http://localhost:8101",
    "http://localhost:8102",
    "http://localhost:8103",
]


async def drive_phase(phase: str, clients: Iterable[httpx.AsyncClient]) -> list[dict]:
    async def _one(c: httpx.AsyncClient) -> dict:
        r = await c.post("/scenario/phase", json={"phase": phase}, timeout=5.0)
        r.raise_for_status()
        return r.json()

    return await asyncio.gather(*(_one(c) for c in clients))


async def _main(phase: str, urls: list[str]) -> int:
    clients = [httpx.AsyncClient(base_url=u) for u in urls]
    try:
        results = await drive_phase(phase, clients)
    finally:
        for c in clients:
            await c.aclose()
    for u, r in zip(urls, results):
        print(f"{u} -> {r}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True, choices=["baseline", "failure", "recovery"])
    p.add_argument("--urls", nargs="*", default=DEFAULT_INSTRUMENT_URLS)
    args = p.parse_args()
    sys.exit(asyncio.run(_main(args.phase, args.urls)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd vix && pytest tests/test_demo_controller.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add vix/demo_controller.py vix/tests/test_demo_controller.py
git commit -m "feat(vix): demo_controller fans phase transitions to all instruments"
```

---

## Task 9: End-to-end smoke test (opt-in)

**Files:**
- Create: `vix/tests/test_e2e_smoke.py`

- [ ] **Step 1: Write `vix/tests/test_e2e_smoke.py`**

```python
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
    # Drive failure, then call set_temperature, and confirm /measure/temperature returns
    # a value inside the nominal band — exercising the dynamics path end-to-end.
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "failure"}, timeout=5.0).raise_for_status()
    time.sleep(0.5)
    httpx.post("http://localhost:8101/command/temperature", json={"target_temp_c": 35.0}, timeout=5.0).raise_for_status()
    # Allow a few ticks for the temp state to converge
    converged = False
    for _ in range(20):
        time.sleep(0.5)
        v = httpx.get("http://localhost:8101/measure/temperature", timeout=5.0).json()["value"]
        if 34.0 <= v <= 36.0:
            converged = True
            break
    httpx.post("http://localhost:8101/scenario/phase", json={"phase": "baseline"}, timeout=5.0)
    assert converged, "Temperature did not converge into the nominal band after set_temperature(35.0)"
```

- [ ] **Step 2: Verify the marker skips by default**

Run: `cd vix && pytest tests/test_e2e_smoke.py -v`
Expected: 3 skipped

- [ ] **Step 3: Run the entire VIX test suite**

Run: `cd vix && pytest -v`
Expected: 37+ passed, 3 skipped

- [ ] **Step 4: Bring up the stack and run the smoke test manually**

Run:

```bash
docker compose up -d backend vix-temp-controller vix-ph-probe vix-microscopy-imager
sleep 8
LABMIND_E2E=1 pytest vix/tests/test_e2e_smoke.py -v
docker compose down
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add vix/tests/test_e2e_smoke.py
git commit -m "test(vix): opt-in e2e smoke against docker-compose stack"
```

---

## Self-review

**Spec coverage (Issue #6 acceptance criteria):**
| Criterion | Task |
|---|---|
| ≥3 mock instruments | 5 (temp_controller), 6 (ph_probe), 7 (microscopy_imager) |
| Each self-registers | `InstrumentBase.register` (Task 4); verified per-instrument in 5, 6, 7 |
| Each streams analytics on interval | `InstrumentBase.analytics_loop` (Task 4); `VIX_INTERVAL_SECONDS` wired in each `_run` (5, 6, 7) |
| Commands change subsequent readings | Dynamics model in 5 (temp), 6 (ph); imager capture posts image_b64 (7); asserted in tests |
| 3-phase scenario arc | `Scenario` (Task 2) + per-instrument JSON files |
| `demo_controller.py` triggers transitions | Task 8 |
| Catalog YAML per instrument | Already in repo; capabilities aligned in 5, 6, 7 |
| Standalone start (`python {name}.py --port NNNN`) | `main()` + argparse in 5, 6, 7 |
| All start via docker-compose | Existing `docker-compose.yml`; smoke-tested in 9 |
| Pytest tests | 2, 3, 4, 5, 6, 7, 8 each include test files |

**Backend (Issue #3) alignment:**
- All endpoints listed in Issue #3 referenced and respected (analytics, instruments/register, analytics 409 behaviour).
- Reading-key sets match `storage.append_temp_row`, `storage.append_impurity_row`, `analytics.py` `image_b64` branch.
- `last_seen` updates handled by backend, not VIX.
- Instrument IDs follow `{type}_NN` convention so backend's `_resolve_type` fallback works pre-registration.
- CORS not relevant (server-to-server).

**Type/name consistency:**
- `register_measure` / `register_command` signature identical across 4–7.
- `build_readings()` signature identical across 5–7.
- Phase names `baseline`/`failure`/`recovery` used uniformly in scenario JSON, `set_phase` callers, and `demo_controller` `--phase` choices.
- Instrument IDs `temp_controller_01`/`ph_probe_01`/`microscopy_imager_01` match `SCHEMAS.md`.
- Dynamics parameter named `dynamics_alpha` in both `TempController.__init__` and `PhProbe.__init__`.

**Out of scope (intentionally not covered):**
- Real LXI/mDNS, GPIB/USB hardware
- Multi-experiment scheduling
- Auto-advancing scenario timelines (operator drives phases via `demo_controller`)
- Authenticated /scenario/phase (open endpoint on localhost — Issue #6 lists no auth)
