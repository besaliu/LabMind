# VIX Mock Instruments — Code Documentation

**Branch:** `feat/vix-mock-instruments`  
**Issue:** [#6 VIX Mock Instruments](https://github.com/besaliu/LabMind/issues/6) (Module 5 of the LabMind PRD)  
**Tests:** 48 passing + 3 opt-in E2E skips  
**Files:** 26 new files under `vix/`

---

## What This Module Does

VIX (Virtual Instrument Interface) simulates real networked lab instruments for the LabMind hackathon demo. Real LXI lab instruments self-announce over a network and expose HTTP endpoints — VIX mocks that exact behavior for three crystal-growth instruments so the full LabMind AI agent loop can be demonstrated without physical hardware.

Each mock instrument:
1. **Self-registers** with the FastAPI backend on startup
2. **Streams analytics** every N seconds (configurable via env var)
3. **Accepts control commands** from the AI agent via MCP tools
4. **Drives a 3-phase demo arc** (baseline → failure → recovery) via scenario files

The headline behavior: when the agent issues a `set_temperature(35.0)` command during the `failure` phase, the temperature readings converge toward 35°C over the next several ticks and the `status` field in the CSV automatically flips from `critical` → `warning` → `nominal` — **without anyone manually changing the phase**. Status is derived from the actual readings vs thresholds, not from the scenario label.

---

## Architecture

```
vix/
├── scenario.py          # JSON phase loader + noisy sampling
├── status.py            # Pure function: readings → nominal|warning|critical
├── instrument_base.py   # Shared FastAPI app + lifecycle (all instruments inherit this)
├── temp_controller.py   # Port 8101, setpoint dynamics
├── ph_probe.py          # Port 8102, pH dynamics
├── microscopy_imager.py # Port 8103, async PNG generation
├── demo_controller.py   # CLI fan-out: advance all 3 instruments' scenario phase at once
├── scenarios/
│   ├── temp_controller.json
│   ├── ph_probe.json
│   └── microscopy_imager.json
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── tests/
    ├── conftest.py               # MockBackend + async fixtures
    ├── test_scenario.py          # 8 tests
    ├── test_status.py            # 10 tests
    ├── test_instrument_base.py   # 11 tests
    ├── test_temp_controller.py   # 7 tests
    ├── test_ph_probe.py          # 5 tests
    ├── test_microscopy_imager.py # 6 tests
    ├── test_demo_controller.py   # 1 test
    └── test_e2e_smoke.py         # 3 tests (skipped unless LABMIND_E2E=1)
```

Every HTTP endpoint exposed by VIX instruments corresponds to a command in `instruments/catalog/*.yaml` — those pre-existing YAML files are what the FastMCP server reads to auto-register agent tools. VIX was written to conform to those contracts exactly.

---

## `vix/scenario.py` — Phase-Based Reading Generator

Loads a JSON file describing three scenario phases and exposes deterministic-with-noise sampling per metric.

### JSON Format

```json
{
  "thresholds": {
    "temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]},
    "setpoint_c":    {"nominal": [32.0, 38.0], "warning": [30.0, 40.0]}
  },
  "baseline": {
    "readings": {
      "temperature_c": {"mean": 35.0, "noise": 0.1},
      "setpoint_c":    {"mean": 35.0, "noise": 0.0}
    }
  },
  "failure": {
    "readings": {
      "temperature_c": {"mean": 38.5, "noise": 0.3},
      "setpoint_c":    {"mean": 35.0, "noise": 0.0}
    }
  },
  "recovery": { "..." }
}
```

`thresholds` are loaded as a public attribute and consumed by `compute_status`. `noise: 0.0` returns the exact mean with no floating-point drift. Phases beyond `baseline/failure/recovery` can be added freely — the only required phase is `baseline`.

### Public API

| Member | Description |
|---|---|
| `Scenario(spec_path, rng=None)` | Load JSON. Raises `ValueError` if no `baseline` phase. |
| `.current_phase` | Property. String name of the active phase. |
| `.thresholds` | Dict of per-metric threshold bands. Passed to `compute_status`. |
| `.set_phase(phase)` | Switch to a different phase. Raises `ValueError` for unknown phase. |
| `.sample(metric)` | Return `mean ± uniform(noise)` for the metric in the active phase. Raises `KeyError` if metric undefined for this phase. |
| `.phase_spec(phase=None)` | Return the raw dict for a phase (used by `MicroscopyImager` to read image generator params). |

Pass `rng=random.Random(0)` in tests for deterministic output.

---

## `vix/status.py` — Threshold-Derived Status

A pure, side-effect-free function. Takes a readings dict and a thresholds dict, returns the **worst** status across all metrics.

```python
def compute_status(readings: dict, thresholds: dict) -> str:
    # Returns "nominal", "warning", or "critical"
```

### Rules

- **Threshold bounds are inclusive** on both ends.
- **Worst-metric wins**: if temperature is `nominal` but pH is `critical`, result is `critical`.
- **Unknown metrics are ignored**: a reading key with no threshold entry has no effect.
- **Non-numeric values are ignored**: strings (like `image_b64`), booleans, and None do not contribute. Note: `bool` is a subclass of `int` in Python, so the check is `isinstance(value, bool)` first, then `isinstance(value, (int, float))`.

### Threshold Band Logic

```
     critical  |  warning  |  nominal  |  warning  |  critical
  ─────────────┼───────────┼───────────┼───────────┼────────────
             warn_lo     nom_lo      nom_hi     warn_hi
```

Anything inside `[nom_lo, nom_hi]` → nominal. Inside `[warn_lo, warn_hi]` but outside nominal → warning. Outside the warning band entirely → critical.

### Why This Matters for the Demo

The `status` field in every analytics POST to the backend is computed here. When the AI agent commands `set_temperature(35.0)` during the failure phase, the actual `temperature_c` reading starts converging toward 35°C. As soon as it crosses into `[33, 37]`, `compute_status` returns `warning`; when it crosses into `[34, 36]`, it returns `nominal`. This happens automatically, with no operator intervention.

---

## `vix/instrument_base.py` — Shared Base Class

Every VIX instrument inherits from `InstrumentBase`. It owns the FastAPI app, the lifecycle (register + analytics loop), the HTTP dispatch tables, and the `/scenario/phase` control endpoint.

### Class Variables (override in subclasses)

```python
class InstrumentBase:
    instrument_type: str = ""       # e.g. "temp_controller"
    instrument_id:   str = ""       # e.g. "temp_controller_01"
    name:            str = ""       # human-readable
    capabilities:    list[str] = [] # what the agent can call via MCP
```

### Constructor

```python
def __init__(self, scenario, port, backend_client, interval_seconds=30.0):
```

- `scenario`: a loaded `Scenario` instance
- `port`: the port this instrument is listening on (used in registration payload)
- `backend_client`: an `httpx.AsyncClient` pointing at the backend — injected for testability
- `interval_seconds`: how often to POST analytics (default 30s, overridden to 3s in tests)

### Registration (`register`)

POSTs to `POST /api/instruments/register`:
```json
{
  "instrument_id": "temp_controller_01",
  "type": "temp_controller",
  "name": "Crystal Growth Temperature Controller",
  "port": 8101,
  "capabilities": ["read_temperature", "set_temperature", "read_cooling_rate", "set_cooling_rate"]
}
```

Retries every `interval_seconds` until the backend returns 2xx. Instruments can start before the backend is ready — they'll keep retrying silently.

### Analytics Loop (`analytics_loop`)

Every `interval_seconds`:
1. Calls `self.build_readings()` (implemented by each subclass)
2. Calls `compute_status(readings, self.scenario.thresholds)` → `"nominal"|"warning"|"critical"`
3. POSTs to `POST /api/analytics`:
   ```json
   {
     "instrument_id": "temp_controller_01",
     "timestamp": "2026-05-15T22:00:03Z",
     "readings": {"temperature_c": 35.04, "setpoint_c": 35.0, "cooling_rate_c_per_hour": 0.5},
     "status": "nominal"
   }
   ```
4. If backend returns **409** (no active experiment): logs at DEBUG, keeps going.
5. Any other error: logs at WARNING, keeps going. The loop never crashes.

### HTTP Routes

| Route | Description |
|---|---|
| `GET /health` | Returns `{"status":"ok","instrument_id":"..."}`. |
| `GET /measure/{metric}` | Calls the registered handler for that metric. Returns 404 if metric unknown. |
| `POST /command/{action}` | Calls the registered handler with the request body. Supports both sync and async handlers. Returns 404 if action unknown. |
| `POST /scenario/phase` | Body: `{"phase":"failure"}`. Calls `self.scenario.set_phase(phase)`. Returns 400 if phase unknown. |

### Handler Registration (subclass API)

```python
self.register_measure("temperature", lambda: {
    "value": self._next_temperature(), "unit": "C", "timestamp": self._now(),
})
self.register_command("temperature", self._set_temperature)
```

---

## `vix/temp_controller.py` — Temperature Controller (Port 8101)

The most complex instrument because of the **dynamics model**: a setpoint command doesn't snap the temperature immediately — it sets a target and each subsequent reading converges toward it.

### Registration

```
instrument_id: temp_controller_01
type: temp_controller
capabilities: read_temperature, set_temperature, read_cooling_rate, set_cooling_rate
port: 8101
```

### Measures

| Endpoint | Returns |
|---|---|
| `GET /measure/temperature` | `{"value": 35.04, "unit": "C", ...}` |
| `GET /measure/setpoint` | `{"value": 35.0, "unit": "C", ...}` |
| `GET /measure/cooling_rate` | `{"value": 0.5, "unit": "C/h", ...}` |

### Commands

| Endpoint | Body | Effect |
|---|---|---|
| `POST /command/temperature` | `{"target_temp_c": 34.0}` | Sets `_setpoint_override`; subsequent temperature readings converge to 34.0 |
| `POST /command/cooling_rate` | `{"rate_c_per_hour": 1.5}` | Immediately overrides cooling rate readings |

### Dynamics Model

```python
def _next_temperature(self) -> float:
    sample = self.scenario.sample("temperature_c")
    if self._setpoint_override is None:
        self._temp_state = sample
        return sample
    if self._temp_state is None:
        self._temp_state = sample
    self._temp_state += self._alpha * (self._setpoint_override - self._temp_state)
    return self._temp_state
```

With `alpha=0.4` (production) and starting state 38.5, target 35.0:

| Tick | State | Status |
|---|---|---|
| 0 | 38.5 | critical |
| 1 | 37.1 | critical (>37) |
| 2 | 36.3 | warning |
| 3 | 35.8 | nominal |
| 4 | 35.5 | nominal |

With `alpha=1.0` (tests), state snaps to target in a single tick.

### SCENARIO Env Var

```python
initial_phase = os.environ.get("SCENARIO", "baseline")
if initial_phase != "baseline":
    scenario.set_phase(initial_phase)
```

docker-compose sets `SCENARIO=baseline` by default. Override with `SCENARIO=failure` to start instruments already in the failure phase.

---

## `vix/ph_probe.py` — pH and Saturation Probe (Port 8102)

Structurally identical to TempController but for solution chemistry.

### Registration

```
instrument_id: ph_probe_01
capabilities: read_ph, read_saturation, add_buffer
port: 8102
```

### Measures

| Endpoint | Returns |
|---|---|
| `GET /measure/ph` | `{"value": 7.1, "unit": "pH", ...}` |
| `GET /measure/saturation` | `{"value": 78.0, "unit": "%", ...}` |

### Commands

| Endpoint | Body | Effect |
|---|---|---|
| `POST /command/buffer` | `{"target_ph": 7.0, "volume_ml": 5.0}` | Sets `_ph_override`; pH readings converge toward 7.0 |

### `build_readings` — What Gets POSTed to Backend

```python
def build_readings(self) -> dict:
    return {
        "ph": self._next_ph(),
        "saturation_pct": self.scenario.sample("saturation_pct"),
        "impurity_ppm": self.scenario.sample("impurity_ppm"),
    }
```

All three keys land in `impurity.csv` via `backend/storage.py`'s `append_impurity_row`.

---

## `vix/microscopy_imager.py` — Crystal Microscopy Imager (Port 8103)

No dynamics. The main feature is the async `capture_image` command, which renders a phase-dependent synthetic PNG and delivers it to the backend.

### Registration

```
instrument_id: microscopy_imager_01
capabilities: capture_image, read_clarity_score, read_defect_classification
port: 8103
```

### Measures (periodic analytics tick)

| Endpoint | Returns |
|---|---|
| `GET /measure/clarity` | `{"value": 92.0, "unit": "%", ...}` |
| `GET /measure/defects` | `{"value": 1, "unit": "count", ...}` |

### `capture_image` Command (Async)

```python
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
        pass  # caller still gets the image even if backend is down
    return {"ok": True, "image_b64": b64}
```

The backend decodes `image_b64` and writes it to `labmind-data/experiments/<run_id>/microscope.png`.

### PNG Rendering

| Phase | base_color | noise_amp | defect_blobs | Appearance |
|---|---|---|---|---|
| baseline | [200, 220, 255] | 5 | 0 | Clean blue-tinted square |
| failure | [200, 180, 180] | 35 | 12 | Brown, noisy, red defect spots |
| recovery | [205, 210, 235] | 12 | 3 | Mostly clean, few defects |

---

## `vix/demo_controller.py` — Phase Transition CLI

Advances all three instruments to a new scenario phase simultaneously.

```python
async def drive_phase(phase: str, clients: Iterable[httpx.AsyncClient]) -> list[dict]:
    async def _one(c):
        r = await c.post("/scenario/phase", json={"phase": phase}, timeout=5.0)
        r.raise_for_status()
        return r.json()
    return await asyncio.gather(*(_one(c) for c in clients))
```

**Usage:**
```bash
python -m vix.demo_controller --phase failure
python -m vix.demo_controller --phase recovery
python -m vix.demo_controller --phase baseline
```

---

## `vix/scenarios/*.json` — Scenario Files

Each scenario file defines per-phase reading distributions and thresholds. The three phases cover the complete demo arc:

| Phase | What it represents | Typical status |
|---|---|---|
| `baseline` | Good crystal conditions, stable experiment | nominal |
| `failure` | Something went wrong — temp spike, pH drop, impurity surge | critical |
| `recovery` | Agent intervened, conditions improving | warning → nominal |

### temp_controller.json thresholds

```json
"temperature_c": {"nominal": [34.0, 36.0], "warning": [33.0, 37.0]}
```

### ph_probe.json thresholds

```json
"ph":             {"nominal": [6.8, 7.4],  "warning": [6.5, 7.6]},
"saturation_pct": {"nominal": [75.0, 80.0],"warning": [70.0, 85.0]},
"impurity_ppm":   {"nominal": [0.0, 30.0], "warning": [0.0, 50.0]}
```

### microscopy_imager.json thresholds

```json
"clarity_pct":  {"nominal": [85.0, 100.0], "warning": [70.0, 100.0]},
"defect_count": {"nominal": [0.0, 3.0],    "warning": [0.0, 8.0]}
```

---

## `vix/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /opt
COPY . /opt/vix
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt
WORKDIR /opt/vix
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "temp_controller.py", "--port", "8101"]
```

`COPY . /opt/vix` puts the package at `/opt/vix/`. `PYTHONPATH=/opt` makes `from vix.instrument_base import ...` resolve. `WORKDIR /opt/vix` means `python temp_controller.py --port 8101` finds the script directly. The `CMD` is overridden per-service in docker-compose.

---

## Tests

### Test Infrastructure (`vix/tests/conftest.py`)

```python
class MockBackend:
    registrations: list[dict]  # captures every /register POST
    analytics: list[dict]      # captures every /analytics POST
    reject_analytics: bool     # set True to simulate 409 (no active experiment)
    app: FastAPI               # the mock backend ASGI app
```

Used via `httpx.ASGITransport(app=mock_backend.app)` — no real network, no real filesystem. Tests are fully async via `pytest-asyncio` with `asyncio_mode = auto`.

### Test Coverage Summary

| File | Tests | What's covered |
|---|---|---|
| `test_scenario.py` | 8 | Phase switching, sampling bounds, zero-noise, error cases |
| `test_status.py` | 10 | All three levels, inclusive bounds, worst-metric-wins, bool/string exclusion |
| `test_instrument_base.py` | 11 | Health, register, analytics timing, 409 survival, measure/command dispatch, async commands, phase endpoint |
| `test_temp_controller.py` | 7 | Registration payload, measure endpoints, dynamics convergence, SCENARIO env var |
| `test_ph_probe.py` | 5 | Registration, baseline range, build_readings keys, failure status, add_buffer dynamics |
| `test_microscopy_imager.py` | 6 | Registration, clarity/defects measures, no image_b64 in periodic tick, failure status, async capture |
| `test_demo_controller.py` | 1 | Fan-out to all 3 instruments, correct payload, all respond |
| `test_e2e_smoke.py` | 3 (skipped) | Registry contains all 3, phase changes reading, set_temperature converges |

### Running Tests

```bash
# All unit tests (from repo root)
cd vix
python -m pytest -v
# Expected: 48 passed, 3 skipped

# E2E smoke (requires docker compose stack running)
docker compose up -d backend vix-temp-controller vix-ph-probe vix-microscopy-imager
LABMIND_E2E=1 python -m pytest vix/tests/test_e2e_smoke.py -v
```

---

## Backend Contract Alignment

VIX was built against the FastAPI backend (Issue #3). Key contracts:

| Backend code | VIX conformance |
|---|---|
| `append_temp_row` reads `temperature_c`, `setpoint_c` | TempController always emits both |
| `append_impurity_row` reads `impurity_ppm`, `saturation_pct`, `ph` | PhProbe always emits all three |
| `analytics.py` reads `readings.get("image_b64")` | MicroscopyImager only sends this on `capture_image`, not every tick |
| `_resolve_type()` strips `_NN` suffix from instrument_id | All IDs follow `{type}_01` convention |
| Returns 409 when no active experiment | All instruments log at debug and keep streaming |
| `upsert_instrument` expects `{instrument_id, type, name, port, capabilities}` | `InstrumentBase.register()` sends exactly these keys |

---

## Known Limitations

- **Double-advance per tick**: `build_readings()` and `/measure/{metric}` both advance the dynamics state independently. At demo cadence (30s interval, occasional agent reads), this is unobservable and was left as-is intentionally.
