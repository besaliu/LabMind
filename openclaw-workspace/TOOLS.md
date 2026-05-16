# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the LabMind MCP tools and instrument setup.

## Core MCP Tools

| Tool | Purpose |
|------|---------|
| `list_experiment_reports()` | Read all past experiment reports (front matter + body) for similarity comparison |
| `get_experiment(run_id)` | Read experiment metadata and status |
| `get_temperature_curve(run_id)` | Read temperature readings over time |
| `get_impurity_log(run_id)` | Read impurity/pH readings over time |
| `get_microscopy_image(run_id)` | Read latest microscopy image (base64 PNG) |
| `get_microscopy_log(run_id)` | Read clarity_pct and defect_count time-series |
| `compare_runs(run_a, run_b)` | Side-by-side comparison of two runs |
| `log_intervention(run_id, action, reasoning)` | Append an action to the audit trail |
| `finalize_experiment(run_id, report, outcome, key_findings)` | Persist morning report with structured front matter |

## Dynamic Instrument Tools

Registered automatically when YAML entries exist in `/instruments/catalog/`. Naming pattern: `{instrument_type}_{command_name}`.

Examples:
- `temp_controller_set_temperature(target_temp_c)`
- `temp_controller_read_temperature()`
- `ph_probe_add_buffer(target_ph, volume_ml)`
- `ph_probe_read_ph()`
- `microscopy_imager_capture_image()`

## Backend API

Call via HTTP when MCP tools don't cover the need:

- `GET http://localhost:8000/api/experiments/current` — current experiment state
- `POST http://localhost:8000/api/experiments/{run_id}/confirm` — confirm experiment after similarity block
- `GET http://localhost:8000/api/instruments` — list registered instruments

## Port Assignments

| Service | Port |
|---------|------|
| FastAPI backend | 8000 |
| FastMCP server (SSE) | 8001 |
| temp_controller_01 | 8101 |
| ph_probe_01 | 8102 |
| microscopy_imager_01 | 8103 |

## Instrument Catalog Location

`/instruments/catalog/{instrument_type}.yaml` — write new entries here when a new instrument type is encountered. The MCP server watches this directory and registers tools within ~2 seconds.

---

Add whatever helps you do your job. This is your cheat sheet.

## Related

- [Agent workspace](/concepts/agent-workspace)
