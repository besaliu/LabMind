# LabMind — DGX Spark Setup Guide

Everything runs locally. Nothing leaves the machine.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | 24+ | All services run in containers |
| Python | 3.10+ | For the MCP server (runs outside Docker) |
| OpenClaw | latest | NVIDIA's agentic CLI — spawns the MCP server |
| Ollama | latest | Serves the local model |

---

## 1. Clone the repo

```bash
git clone https://github.com/besaliu/LabMind.git ~/LabMind
cd ~/LabMind
```

---

## 2. Create required path symlinks

The MCP server runs **outside Docker** (OpenClaw spawns it directly) and expects two absolute paths. Create symlinks so both Docker containers and the MCP server see the same data:

```bash
sudo ln -s ~/LabMind/labmind-data /labmind-data
sudo ln -s ~/LabMind/instruments /instruments
```

Verify:

```bash
ls /labmind-data/experiments    # should list run_001, run_002
ls /instruments/catalog         # should list temp_controller.yaml, etc.
```

---

## 3. Pull the model

```bash
ollama pull nemotron-super-49b
```

Verify:

```bash
ollama run nemotron-super-49b "Hello"
```

---

## 4. Install MCP server dependencies

The MCP server runs outside Docker — OpenClaw spawns it via `.openclaw/mcp.json`. Install its Python dependencies:

```bash
pip install -r mcp_server/requirements.txt
```

Verify Python version is 3.10 or higher:

```bash
python3 --version
```

---

## 5. Start all backend services

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

Wait for the backend to be healthy:

```bash
docker compose ps   # backend should show "healthy"
```

---

## 6. Start OpenClaw

From the repo root:

```bash
openclaw
```

OpenClaw reads `.openclaw/mcp.json` and spawns the MCP server automatically. It loads `AGENT.md` as the agent's system prompt.

The agent should greet you:

```
LabMind online. RAG database contains N past experiments.
Monitoring for pending runs. Ask me anything.
```

---

## 7. Access the upload dashboard

Open a browser and go to:

```
http://<spark-tailscale-ip>:8000
```

Or from the Spark itself:

```
http://localhost:8000
```

This serves the experiment upload form. Drop a `.md` or `.yaml` experiment document to start a new run. The agent picks it up automatically via the monitoring loop.

**OpenClaw chat UI** is at port 18789 but binds to 127.0.0.1 — access it via SSH tunnel:

```bash
ssh -N -L 18789:127.0.0.1:18789 asus@<spark-tailscale-ip>
```

Then open `http://localhost:18789` in your browser.

---

## 8. Run a demo experiment

### Option A — Query seed data (no upload needed)

The repo ships with two completed runs:

- `run_001` — KDP crystal growth, slow cooling, success
- `run_002` — KDP crystal growth, fast cooling, temperature spike, partial failure

Try in the OpenClaw chat:

```
What happened in run_002?
```

```
Have we ever grown KDP crystals above 35°C?
```

### Option B — Upload a new experiment document

1. Open `http://localhost:8000` in a browser
2. Drag and drop an experiment `.md` file (see `example_experiment.md` for the format)
3. The agent detects the pending run, runs a RAG similarity check, and either:
   - Asks for confirmation in the chat if a similar past run is found (similarity ≥ 0.85)
   - Registers instruments and enters monitoring mode

---

## 9. Trigger a VIX scenario (demo a problem)

Each mock instrument supports a `failure` scenario that simulates a real problem. Switch a running instrument to failure mode:

```bash
# Trigger a temperature spike
curl -X POST http://localhost:8101/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'

# Trigger pH drift
curl -X POST http://localhost:8102/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'

# Trigger crystal clarity drop
curl -X POST http://localhost:8103/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'
```

The agent will detect the anomaly within one monitoring cycle (60 seconds) and take corrective action. Switch back to normal:

```bash
curl -X POST http://localhost:8101/scenario/phase -H "Content-Type: application/json" -d '{"phase": "baseline"}'
```

---

## 10. Directory layout

```
~/LabMind/
  labmind-data/               → symlinked to /labmind-data
    experiments/
      run_001/
        metadata.json         # parameters, thresholds, status, outcome
        temp.csv              # temperature readings (written by backend)
        impurity.csv          # impurity + pH readings (written by backend)
        microscopy.csv        # clarity_pct + defect_count (written by backend)
        microscope.png        # latest crystal image (written by backend)
        interventions.json    # agent action log (written by MCP tool)
        report.md             # morning report (written by finalize_experiment)
    state.json                # active_run_id and pending_run_id pointers

  instruments/                → symlinked to /instruments
    catalog/
      temp_controller.yaml    # instrument tool definitions (read by MCP server)
      ph_probe.yaml
      microscopy_imager.yaml
```

---

## 11. Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LABMIND_DATA` | `/labmind-data` | Root data directory |
| `CATALOG_DIR` | `/instruments/catalog` | Instrument YAML catalog directory |
| `BACKEND_URL` | `http://localhost:8000` | FastAPI backend URL (used by MCP server) |
| `RAG_SERVICE_URL` | `http://localhost:8002` | RAG service URL (used by MCP server) |
| `RAG_SIMILARITY_THRESHOLD` | `0.85` | Similarity score above which a new run is blocked |

All defaults are pre-configured in `.openclaw/mcp.json` and `docker-compose.yml`. Only change them if you run services on different ports.

---

## 12. Troubleshooting

**Agent says RAG is unavailable**
- Check `docker compose ps` — the `rag` container must be running
- Check `docker compose logs rag` for startup errors

**Dynamic instrument tools not appearing in OpenClaw**
- Check that the symlink `/instruments → ~/LabMind/instruments` exists
- Check that catalog YAMLs are in `/instruments/catalog/` (not a subdirectory)
- Verify the YAML follows the schema in `SCHEMAS.md`

**Backend returns 409 on experiment upload**
- An experiment is already active. Finalize it first, or check `cat /labmind-data/state.json` to see the active run ID.

**VIX instruments not registering**
- Check `docker compose logs vix-temp-controller` for connection errors
- Verify the backend is healthy: `curl http://localhost:8000/health`

**MCP server not finding experiment data**
- Check the symlink: `ls /labmind-data/experiments` must list run directories
- Check `LABMIND_DATA` env var in `.openclaw/mcp.json`
