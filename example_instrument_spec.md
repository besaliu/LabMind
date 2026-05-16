# Instrument API Specification: Solution Conductivity Probe

**Instrument:** VIX-Conductivity-04
**Base URL:** `http://localhost:8104`

This probe measures the electrical conductivity of the growth solution. As KDP crystals form,
potassium and phosphate ions leave solution and conductivity drops — making it a real-time proxy
for how much material has crystallised out. Paste this document into the LabMind chat to have the
agent generate and register MCP tools for this instrument automatically.

---

## Endpoints

### GET /measure/conductivity
Returns the current conductivity and solution temperature.

**Response:**
```json
{
  "conductivity_ms_cm": 12.3,
  "temperature_c": 35.1,
  "alert_threshold_ms_cm": 9.0,
  "status": "nominal",
  "timestamp": "2026-05-16T02:15:00Z"
}
```

`conductivity_ms_cm` is in millisiemens per centimetre. For a KDP solution at target
concentration, expect ~12–14 mS/cm at the start of a run. A reading below 9 mS/cm indicates
significant crystallisation has occurred and `status` will be `"alert"`.

### POST /command/set_alert_threshold
Sets the conductivity threshold below which the probe reports `status: "alert"`.

**Request body:**
```json
{ "threshold_ms_cm": 9.0 }
```

**Response:**
```json
{ "ok": true, "threshold_ms_cm": 9.0 }
```

### POST /scenario/phase
Switches the instrument into a simulated scenario phase (for demo/testing).

**Request body:**
```json
{ "phase": "baseline" }
```

Valid phases:
- `baseline` — steady ~12.8 mS/cm, crystallisation not yet started
- `crystallising` — gradual drop to ~8.5 mS/cm, active crystal growth
- `complete` — stable low ~7.2 mS/cm, run finished
