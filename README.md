# LabMind

AI lab overseer agent for air-gapped research environments. Runs locally on a DGX Spark with OpenClaw and Ollama. Everything stays on the machine — nothing leaves the host.

## What it does

- **Lab Assistant Mode**: Ask questions about past experiments in natural language — LabMind reads all past experiment reports and responds with specific findings.
- **Experiment Mode**: Upload an experiment doc → agent checks for duplicate work by comparing past report parameters → registers instruments → monitors overnight → detects anomalies → remediates autonomously → generates a morning report.

## Architecture

```
Researcher
    │
    ├─► Upload UI (backend :8000)
    │
    ▼
FastAPI Backend (:8000) ──── /labmind-data/
    │
    ▼
VIX mock instruments (:8101–8103)

OpenClaw (:18789, loopback) ◄── stdio ── mcp-remote ◄── SSE ── FastMCP (Docker :8001)
    │
    └── AGENT.md (system prompt) + Ollama (chat model, host :11434)
```

The FastMCP server runs as a Docker service on port 8001 (HTTP/SSE). OpenClaw connects to it via `mcp-remote` (an npm bridge), registered using MCPorter. All five services start with `docker compose up`.

## Prerequisites

All of these must be installed and working on the Spark host before you start the setup steps.

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | 24+ | All services (backend, MCP server, VIX instruments) |
| Node.js + npm | 18+ | OpenClaw, MCPorter, and mcp-remote |
| OpenClaw | latest | `npm i -g openclaw` |
| MCPorter | latest | `npm i -g mcporter` |
| Ollama | latest | Chat model for the agent |
| Tailscale | latest | Required only if you want to reach the Spark from another machine |

Quick prerequisite check on the Spark:

```bash
docker --version && docker compose version
node --version && npm --version  # must be Node 18+
openclaw --version
mcporter --version
ollama --version
tailscale ip -4              # optional; remember this IP for the SSH tunnel later
docker ps                    # if this errors with permission denied, add yourself to the docker group:
                             # sudo usermod -aG docker $USER && newgrp docker
```

## Setup (DGX Spark)

### 1. Clone the repo

```bash
git clone https://github.com/besaliu/LabMind.git ~/LabMind
cd ~/LabMind
```

### 2. Pull the chat model

```bash
# Chat model — should already exist if your Spark was pre-provisioned
ollama list | grep nemotron-3-super         # confirm it's present
# If it's missing, pull it (this is large — 86 GB):
ollama pull nemotron-3-super:latest
ollama run nemotron-3-super:latest "Hello"
```

Configure OpenClaw/Nemoclaw inference to use the chat-model tag (during onboarding choose **Local Ollama**, or at runtime: `openshell inference set --provider ollama --model nemotron-3-super:latest`). The repo does not pin the model in `.openclaw/` — only MCP and sandbox settings live there.

### 3. Start all services

```bash
docker compose up -d --build
docker compose ps           # all five services should be "running"; backend should be "healthy"
```

| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8000 | FastAPI — experiment upload, state, analytics |
| `mcp` | 8001 | FastMCP server — MCP tools over HTTP/SSE |
| `vix-temp-controller` | 8101 | Mock temperature controller |
| `vix-ph-probe` | 8102 | Mock pH probe |
| `vix-microscopy-imager` | 8103 | Mock microscopy imager |

Smoke check:

```bash
curl -s http://localhost:8000/health   # {"status":"ok"}
curl -s http://localhost:8001/sse      # SSE stream opens — Ctrl-C to stop
```

### 4. Configure OpenClaw and start the gateway

```bash
openclaw configure
```

You can skip channel setup if you are only testing locally.

```bash
openclaw gateway
```

Confirm the gateway is running:

```bash
openclaw gateway status
openclaw doctor
```

Once these commands succeed, the runtime is active.

### 5. Register the MCP server with MCPorter

```bash
npm i -g mcporter
mcporter config add labmind --command 'npx mcp-remote "http://localhost:8001/sse"'
```

Confirm it is registered:

```bash
mcporter config list
```

Verify tool access — list all exposed tools and schemas:

```bash
mcporter list
```

If this returns `get_experiment`, `list_experiment_reports`, `get_temperature_curve`, `compare_runs`, `log_intervention`, `finalize_experiment`, plus dynamic instrument tools, the MCP connection is working.

### 6. Start OpenClaw

From the repo root:

```bash
openclaw
```

OpenClaw reads `.openclaw/mcp.json`, connects to the MCP server via `mcp-remote`, and loads `AGENT.md` as the agent system prompt.

### 7. Access the UI

**Experiment upload** (built into the backend, no separate dashboard):


```
http://localhost:8000        # if you are on the Spark itself
http://<spark-tailscale-ip>:8000   # from your laptop over Tailscale
```

You can find `<spark-tailscale-ip>` with `tailscale ip -4` on the Spark.

**OpenClaw chat UI** binds to `127.0.0.1:18789` (loopback only — not exposed over Tailscale directly). Tunnel from your laptop:

```bash
# Replace <spark-user> with your actual SSH login on the Spark (e.g. asus, ubuntu, etc.)
ssh -N -L 18789:127.0.0.1:18789 <spark-user>@<spark-tailscale-ip>
```

Leave that terminal open, then on your laptop open `http://localhost:18789`.

## Demo

### Query seed data (no upload)

- `run_001` — KDP crystal growth, slow cooling (0.5°C/hr), success
- `run_002` — KDP crystal growth, fast cooling (1.5°C/hr), temperature spike, partial failure

In the OpenClaw chat:

```
What happened in run_002?
```

```
Have we ever grown KDP crystals above 35°C?
```

### Upload a new experiment

1. Open `http://localhost:8000`
2. Drop an experiment `.md` file (see `example_experiment.md`)
3. The agent detects the pending run, runs a similarity check against past experiment reports, and either asks for confirmation in chat (similar parameters found) or registers instruments and enters monitoring mode

### Trigger a VIX failure scenario

```bash
# Temperature spike
curl -X POST http://localhost:8101/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'

# pH drift
curl -X POST http://localhost:8102/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'

# Crystal clarity drop
curl -X POST http://localhost:8103/scenario/phase -H "Content-Type: application/json" -d '{"phase": "failure"}'
```

The agent should detect the anomaly within one monitoring cycle (~60s). Reset to baseline:

```bash
curl -X POST http://localhost:8101/scenario/phase -H "Content-Type: application/json" -d '{"phase": "baseline"}'
```

Optional CLI helper (posts scenario phases to all VIX services):

```bash
python vix/demo_controller.py
```

## Repository structure

```
LabMind/
├── AGENT.md                 # OpenClaw agent system prompt
├── SCHEMAS.md               # Shared data format contracts
├── example_experiment.md    # Sample experiment upload format
├── docker-compose.yml       # backend + 3 vix services
├── .openclaw/
│   ├── mcp.json             # MCP server spawn config (stdio)
│   └── sandbox.yaml         # Filesystem and network sandbox rules
├── backend/                 # FastAPI backend (port 8000)
├── mcp_server/              # FastMCP server (Docker :8001, HTTP/SSE)
├── vix/                     # Mock instrument servers (8101-8103) + demo_controller.py
├── instruments/catalog/     # Instrument YAML tool definitions (agent-writable)
├── docs/                    # Plans, handoffs, design notes
└── labmind-data/
    ├── experiments/         # One directory per run (seed: run_001, run_002)
    └── instruments/         # registry.json
```

### Data layout (per run)

```
labmind-data/experiments/run_XXX/
  metadata.json         # parameters, thresholds, status, outcome
  temp.csv              # temperature (backend)
  impurity.csv          # impurity + pH (backend)
  interventions.json    # agent audit trail (MCP log_intervention)
  report.md             # morning report with YAML front matter (finalize_experiment MCP tool)
  microscope.png        # latest image (backend)
state.json              # active_run_id, pending_run_id
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LABMIND_DATA` | `/labmind-data` | Root data directory (mounted volume inside Docker) |
| `CATALOG_DIR` | `/instruments/catalog` | Instrument YAML catalog (mounted volume inside Docker) |
| `BACKEND_URL` | `http://backend:8000` | FastAPI URL used by the MCP container |
| `MCP_PORT` | `8001` | Port the FastMCP SSE server listens on |

Defaults are set in `docker-compose.yml`.

## Troubleshooting

**Dynamic instrument tools missing in OpenClaw**

- Catalog files: `ls instruments/catalog/` from the repo root must list the three shipped YAMLs.
- `docker compose logs mcp -f` — the file watcher picks up YAML changes within ~2s; check logs for registration messages.
- Verify the connection: `mcporter list` — if tools appear here but not in OpenClaw, restart OpenClaw.

**Backend returns 409 on upload**

- An experiment is already active. Check `cat labmind-data/state.json`; if you want to abandon it, edit `state.json` to set `"active_run_id": null` and update the run's `metadata.json` `status` to `"completed"` or delete the run directory.

**VIX instruments not registering**

- `docker compose logs vix-temp-controller` (and the other two).
- `curl http://localhost:8000/api/instruments` should list all three within 30s of `docker compose up`.

**MCP server cannot read experiment data**

- `docker compose logs mcp` — check for startup errors.
- `ls labmind-data/experiments` from the repo root must list run directories; the volume mount exposes this inside the container as `/labmind-data/experiments`.

**MCPorter shows no tools / mcp-remote connection refused**

- Confirm `docker compose ps` shows the `mcp` service as running.
- `curl http://localhost:8001/sse` should open an SSE stream; if it fails the container is not up.
- Re-run `mcporter config add labmind --command 'npx mcp-remote "http://localhost:8001/sse"'` if the registration was lost.

**Form uploader rejects `.md` files**

- Make sure you have the latest backend image; the upload form's `accept` filter must include `.md`. If not, rebuild: `docker compose up -d --build backend`.

## Known limitations

These are documented gaps in the current implementation — they will not "just work" in the demo and require either manual intervention or pending feature work.

- **No scripted failure timeline.** VIX scenario phases (`baseline`/`failure`/`recovery`) flip only when you `curl` `POST /scenario/phase` manually or run `python vix/demo_controller.py`. There is no scheduler that injects faults at predetermined offsets after an experiment starts.
- **No instrument auto-discovery.** The agent can only register MCP tools for instrument types that already have a YAML in `/instruments/catalog/`. The three shipped types (`temp_controller`, `ph_probe`, `microscopy_imager`) work out of the box; a brand-new instrument type referenced in an experiment doc will not get MCP tools generated automatically.
- **Always-on monitoring is prompt-side only.** AGENT.md instructs the agent to poll `GET /api/experiments/current` every cycle, but nothing in the backend or MCP server forces this. Whether Nemotron actually self-polls overnight without a user nudge is model-dependent — observe behavior before relying on it.
- **No automatic experiment-end trigger.** The agent computes elapsed time itself against `metadata.duration_hours` and decides when to write the morning report. There is no backend-fired "time's up" signal.
- **Microscopy image description requires a vision-capable model.** AGENT.md asks the agent to "describe what you observe" from `get_microscopy_image`. Nemotron-3-Super is text-only — image content will be ignored unless you wire in a multimodal model.

## Data schemas

All shared file formats: [SCHEMAS.md](SCHEMAS.md).

## GitHub issues

- [#1](https://github.com/besaliu/LabMind/issues/1) Parent PRD
- [#3](https://github.com/besaliu/LabMind/issues/3) FastAPI backend
- [#4](https://github.com/besaliu/LabMind/issues/4) FastMCP server
- [#6](https://github.com/besaliu/LabMind/issues/6) VIX mock instruments
- [#8](https://github.com/besaliu/LabMind/issues/8) OpenClaw agent configuration
- [#9](https://github.com/besaliu/LabMind/issues/9) E2E integration + demo
