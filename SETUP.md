# LabMind — DGX Spark Setup Guide

Everything runs locally. Nothing leaves the machine.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | 24+ | All services run in containers |
| Python | 3.10+ | For the MCP server (3.13 recommended) |
| NemoCLAW / OpenClaw | latest | NVIDIA's agentic CLI stack |
| Ollama | latest | Serves Nemotron 3 Super 120B locally |
| Nemotron 3 Super 120B weights | — | Pull via Ollama (see below) |

---

## 1. Pull the model

```bash
ollama pull nemotron-super-120b
```

Verify it responds:

```bash
ollama run nemotron-super-120b "Hello"
```

---

## 2. Install MCP server dependencies

The MCP server runs **outside Docker** — OpenClaw spawns it directly via `.openclaw/mcp.json`. It requires Python 3.10+ available as `python3` on your PATH.

```bash
cd mcp_server
pip install -r requirements.txt
cd ..
```

Verify the right Python is used:

```bash
python3 --version   # must be 3.10 or higher
```

`requirements.txt` includes `fastmcp`, `httpx`, `pyyaml`, and `watchfiles`.

---

## 3. Start all backend services

From the repo root:

```bash
docker compose up -d
```

This starts:

| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8000 | FastAPI — experiment upload, state, analytics |
| `rag` | 8002 | RAG service — vector search over past experiments |
| `vix-temp-controller` | 8101 | Mock temperature controller |
| `vix-ph-probe` | 8102 | Mock pH probe |
| `vix-microscopy-imager` | 8103 | Mock microscopy imager |
| `dashboard` | 5173 | Web dashboard (upload, alerts, chat) |

Wait for the backend health check to pass:

```bash
docker compose ps   # all services should show "healthy" or "running"
```

---

## 4. Start OpenClaw

From the repo root:

```bash
openclaw
```

OpenClaw reads `.openclaw/mcp.json` and spawns the FastMCP server automatically. It loads `AGENT.md` as the agent's system prompt.

You should see the agent greet you with something like:

```
LabMind online. RAG database contains N past experiments.
Monitoring for pending runs. Ask me anything.
```

---

## 5. Run a demo experiment

### Option A — Crystal demo (pre-loaded seed data)

The repo ships with two seed runs:

- `run_001` — KDP crystal growth, success, baseline
- `run_002` — KDP crystal growth with temp spike at hour 3, partial failure

Try asking:

```
What happened in run_002?
```

```
Have we ever grown KDP crystals above 35°C?
```

### Option B — Upload a new experiment document

1. Open the dashboard at `http://localhost:5173`
2. Click **Upload Experiment** and drop a PDF or plain-text doc
3. The agent will detect the pending run, run a RAG similarity check, and either:
   - Block with a warning if a similar run exists (similarity ≥ 0.85)
   - Register instruments and enter monitoring mode

---

## 6. Directory layout

```
/labmind-data/                    # persistent experiment data (Docker volume)
  experiments/
    run_001/
      metadata.json               # parameters, thresholds, status, outcome
      temp.csv                    # temperature readings (written by backend)
      impurity.csv                # impurity + pH readings (written by backend)
      microscope.png              # latest crystal image (written by backend)
      interventions.json          # agent action log (written by MCP tool)
      report.md                   # morning report (written by finalize_experiment)
  state.json                      # active_run_id pointer

/instruments/catalog/             # instrument registry (agent writes here)
  temp_controller.yaml
  ph_probe.yaml
  microscopy_imager.yaml
```

---

## 7. Adding a real instrument

When a real networked instrument is connected to the lab LAN, register it by writing a catalog YAML. The agent will do this automatically from the experiment document — but you can also add one manually:

```bash
cat > /instruments/catalog/my_instrument.yaml << 'EOF'
instrument_type: my_instrument
endpoint_pattern: "http://localhost:{port}"
port: 8110
commands:
  read_value:
    method: GET
    path: /measure/value
    params: []
  set_value:
    method: POST
    path: /command/set
    params:
      - name: target
        type: float
        description: Target value to set
EOF
```

The MCP server detects the new file within 2 seconds and registers `my_instrument_read_value` and `my_instrument_set_value` as live tools — no restart needed.

---

## 8. Environment variables

All services read these variables. Set them in Docker Compose (already configured) or in your shell for local dev.

| Variable | Default | Description |
|----------|---------|-------------|
| `LABMIND_DATA` | `/labmind-data` | Root data directory |
| `CATALOG_DIR` | `/instruments/catalog` | Instrument YAML catalog directory |
| `BACKEND_URL` | `http://localhost:8000` | FastAPI backend URL (used by MCP server) |
| `RAG_SERVICE_URL` | `http://localhost:8002` | RAG service URL (used by MCP server) |
| `RAG_SIMILARITY_THRESHOLD` | `0.85` | Similarity score above which a new run is blocked |

---

## 9. Troubleshooting

**Agent says RAG is unavailable**
- Check `docker compose ps` — the `rag` container must be running
- Check `docker compose logs rag` for startup errors

**Dynamic instrument tools not appearing**
- Check that the YAML file was written to `/instruments/catalog/` (not a subdirectory)
- Check `docker compose logs mcp-server` for YAML parse errors
- Verify the YAML follows the schema in `SCHEMAS.md`

**Backend returns 404 on `/api/experiments/current`**
- No active run exists. Upload an experiment document via the dashboard first.

**Experiment upload returns an error**
- The uploaded document must include a `hypothesis` field. Plain-text format: `hypothesis: <text>`. PDF: the backend extracts the first paragraph as the hypothesis.
