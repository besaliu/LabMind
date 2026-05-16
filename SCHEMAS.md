# LabMind Shared Data Schemas

All modules read and write through `/labmind-data/`. This file is the contract — if you change a schema here, update every module that touches it.

---

## Directory Layout

```
labmind-data/
├── experiments/
│   └── {run_id}/
│       ├── metadata.json
│       ├── temp.csv
│       ├── impurity.csv
│       ├── microscope.png
│       ├── interventions.json
│       └── report.md
├── instruments/
│   └── registry.json
└── chromadb/               # ChromaDB persistence (do not edit manually)

instruments/
└── catalog/
    └── {instrument_type}.yaml
```

---

## Experiment document format (uploaded by researcher)

YAML file uploaded to `POST /api/experiments/upload`. The backend parses this and stores all fields in `metadata.json`. The agent reads `metadata.json` via the `get_experiment` MCP tool.

```yaml
hypothesis: KDP crystals grown at 35°C with slow cooling will produce larger, purer crystals

context: |
  Multi-line scientific background. Why this experiment, what the expected
  mechanism is, what past runs inform it. Used for RAG similarity search
  and agent decision-making throughout the run.

experiment_type: crystallization   # free-form label
duration_hours: 8

instruments:
  - temp_controller
  - ph_probe
  - microscopy_imager

parameters:                         # experiment-specific setup values
  target_temp_c: 35.0
  cooling_rate_c_per_hour: 0.5

stages:                             # ordered phases; agent uses elapsed time to determine current stage
  - name: equilibration
    hours: "0-2"
    description: Hold at target temp. Slight impurity elevation is normal here.
  - name: nucleation
    hours: "2-6"
    description: Critical phase. Treat warning_above as critical. No large adjustments.
  - name: growth
    hours: "6-8"
    description: Monitor impurity closely. Capture microscopy every 30 minutes.

monitoring:                         # per-parameter thresholds with context
  temperature_c:
    target: 35.0
    warning_above: 37.0             # agent notes but does not yet act
    critical_above: 38.0            # agent acts immediately
    warning_below: 33.0
    critical_below: 31.0
    concern: >
      Why this matters and any stage-specific tightening rules.
  impurity_ppm:
    target: 15.0
    warning_above: 35.0
    critical_above: 50.0
    concern: >
      Rising impurity means crystals are dissolving. Correlates with temperature.
  ph:
    target: 7.1
    warning_above: 7.4
    critical_above: 7.6
    warning_below: 6.8
    critical_below: 6.5
    concern: >
      pH above 7.5 causes irreversible KDP hydrolysis.

remediation:                        # agent reads this to determine the correct action per problem type
  temperature_high:
    instrument: temp_controller
    action: reduce_setpoint
    max_step_c: 1.0
    max_total_adjustment_c: 2.0
    note: Never reduce more than 1°C per cycle.
  temperature_low:
    instrument: temp_controller
    action: increase_setpoint
    max_step_c: 0.5
  ph_high:
    instrument: ph_probe
    action: add_buffer
    start_volume_ml: 5.0
  ph_low:
    instrument: ph_probe
    action: add_buffer
    start_volume_ml: 5.0
  impurity_spike:
    instrument: temp_controller
    action: reduce_setpoint
    max_step_c: 0.5

success_criteria:                   # used in morning report outcome section
  - metric: crystal_clarity_pct
    target: ">= 90"
  - metric: final_impurity_ppm
    target: "< 30"

known_risks:                        # agent reads these before deciding to intervene
  - Impurity in hours 2-4 may be elevated during nucleation onset — not a reason to intervene
  - Temperature control lags 2-3 minutes after setpoint change — wait before re-adjusting
```

---

## `metadata.json`

Created by the FastAPI backend when an experiment doc is uploaded. All fields from the experiment doc are stored here verbatim, plus runtime fields added by the backend.

```json
{
  "run_id": "run_001",
  "hypothesis": "KDP crystals grown at 35°C with slow cooling will produce larger, purer crystals",
  "context": "Scientific background and rationale...",
  "experiment_type": "crystallization",
  "duration_hours": 8,
  "instruments": ["temp_controller", "ph_probe", "microscopy_imager"],
  "parameters": {"target_temp_c": 35.0, "cooling_rate_c_per_hour": 0.5},
  "stages": [
    {"name": "equilibration", "hours": "0-2", "description": "..."},
    {"name": "nucleation", "hours": "2-6", "description": "..."}
  ],
  "monitoring": {
    "temperature_c": {
      "target": 35.0,
      "warning_above": 37.0, "critical_above": 38.0,
      "warning_below": 33.0, "critical_below": 31.0,
      "concern": "Why this matters..."
    },
    "impurity_ppm": {"target": 15.0, "warning_above": 35.0, "critical_above": 50.0, "concern": "..."},
    "ph": {"target": 7.1, "warning_above": 7.4, "critical_above": 7.6, "warning_below": 6.8, "critical_below": 6.5, "concern": "..."}
  },
  "remediation": {
    "temperature_high": {"instrument": "temp_controller", "action": "reduce_setpoint", "max_step_c": 1.0, "note": "..."},
    "ph_high": {"instrument": "ph_probe", "action": "add_buffer", "start_volume_ml": 5.0}
  },
  "success_criteria": [
    {"metric": "crystal_clarity_pct", "target": ">= 90"}
  ],
  "known_risks": ["Impurity elevation during hours 2-4 is expected..."],
  "start_time": "2026-05-15T22:00:00Z",
  "end_time": null,
  "status": "active",
  "outcome": null,
  "key_findings": []
}
```

**Status values:** `pending` → `active` → `completed` | `failed`

---

## `temp.csv`

Appended by the FastAPI backend each time a temperature instrument POSTs analytics.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO8601 string | When the reading was taken |
| `temperature_c` | float | Measured temperature in Celsius |
| `setpoint_c` | float | Target temperature setpoint |
| `status` | string | `nominal`, `warning`, `critical` |

Example:
```csv
timestamp,temperature_c,setpoint_c,status
2026-05-15T22:00:00Z,35.0,35.0,nominal
2026-05-15T22:00:30Z,35.1,35.0,nominal
2026-05-15T22:01:00Z,36.8,35.0,warning
```

---

## `impurity.csv`

Appended by the FastAPI backend each time a chemical sensor or pH probe POSTs analytics.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO8601 string | When the reading was taken |
| `impurity_ppm` | float | Impurity concentration in parts per million |
| `saturation_pct` | float | Solution saturation percentage (0–100) |
| `ph` | float | pH reading |
| `status` | string | `nominal`, `warning`, `critical` |

Example:
```csv
timestamp,impurity_ppm,saturation_pct,ph,status
2026-05-15T22:00:00Z,12.3,78.2,7.1,nominal
2026-05-15T22:00:30Z,13.1,78.5,7.0,nominal
2026-05-15T22:01:00Z,67.4,82.1,6.2,critical
```

---

## `microscope.png`

Latest microscopy image from the imaging instrument. Overwritten on each new image reading. PNG format. The MCP tool `get_microscopy_image` returns this as base64.

---

## `interventions.json`

Append-only log of every action the agent takes during an experiment. Written by the MCP tool `log_intervention`.

```json
[
  {
    "timestamp": "2026-05-15T22:01:05Z",
    "action": "set_temperature(instrument_id='temp_controller_01', target_temp_c=34.0)",
    "reasoning": "Temperature rose to 36.8°C, exceeding warning threshold of 36°C. Historical run_002 shows similar drift led to crystal cracking. Reducing setpoint by 1°C to arrest the rise while avoiding thermal shock.",
    "instrument_id": "temp_controller_01",
    "outcome": "Temperature returned to 35.2°C within 4 minutes"
  }
]
```

---

## `report.md`

Generated by the agent on experiment finalization. Markdown format. Rendered by the dashboard Reports view.

Contains: experiment summary, timeline of events, list of interventions with reasoning, outcome assessment, recommendation for next run.

---

## `instruments/registry.json`

Written by the FastAPI backend when an instrument POSTs to `/api/instruments/register`. Updated on each re-registration.

```json
{
  "temp_controller_01": {
    "instrument_id": "temp_controller_01",
    "type": "temp_controller",
    "name": "Crystal Growth Temperature Controller",
    "port": 8101,
    "capabilities": ["read_temperature", "set_temperature", "read_cooling_rate"],
    "registered_at": "2026-05-15T21:58:00Z",
    "last_seen": "2026-05-15T22:05:00Z",
    "status": "online"
  }
}
```

---

## `instruments/catalog/{instrument_type}.yaml`

One file per instrument type. Written by the agent when a new instrument type is encountered. Read by the FastMCP server's file watcher to dynamically register MCP tools.

```yaml
instrument_type: temp_controller
endpoint_pattern: "http://localhost:{port}"
port: 8101
commands:
  read_temperature:
    method: GET
    path: /measure/temperature
    params: []
  set_temperature:
    method: POST
    path: /command/temperature
    params:
      - name: target_temp_c
        type: float
        description: Target temperature in Celsius
  read_cooling_rate:
    method: GET
    path: /measure/cooling_rate
    params: []
```

**Rules:**
- `instrument_type` must be unique and match the `type` field in `registry.json`
- `endpoint_pattern` uses `{port}` as the only substitution variable
- `params` is an empty list `[]` for GET commands
- Tool names registered in MCP follow the pattern `{instrument_type}_{command_name}`

---

## Analytics POST payload

Sent by every VIX instrument to `POST /api/analytics`. Not persisted as a file — the backend routes readings into the appropriate CSV column(s).

```json
{
  "instrument_id": "temp_controller_01",
  "timestamp": "2026-05-15T22:01:00Z",
  "readings": {
    "temperature_c": 36.8,
    "setpoint_c": 35.0,
    "cooling_rate_c_per_hour": 0.5
  },
  "status": "warning"
}
```

The backend maps `readings` keys to CSV columns based on the instrument type. Unknown keys are stored in a catch-all `extra.json` per run (non-blocking).

---

## Port Assignments

| Service | Port |
|---------|------|
| FastAPI backend | 8000 |
| FastMCP server | 8001 |
| React dashboard (dev) | 5173 |
| VIX instrument base | 8100+ |
| temp_controller_01 | 8101 |
| ph_probe_01 | 8102 |
| microscopy_imager_01 | 8103 |
| chemical_stability_01 | 8104 |
| uvvis_spectrophotometer_01 | 8105 |
