# LabMind

AI lab overseer agent for air-gapped research environments. Runs locally on a DGX Spark with OpenClaw and Ollama. Everything stays on the machine — nothing leaves the host.

## What it does

- **Lab Assistant Mode**: Ask questions about past experiments in natural language — LabMind queries its local RAG database and responds.
- **Experiment Mode**: Upload an experiment doc → agent checks for duplicate work → registers instruments → monitors overnight → detects anomalies → remediates autonomously → generates a morning report → logs results to RAG.

## Architecture

```
Researcher
    │
    ├─► Upload UI (backend :8000)
    │
    ▼
FastAPI Backend (:8000) ──── /labmind-data/ ──── RAG service (:8002, ChromaDB + Ollama embeddings)
    │                                                        │
    ▼                                                        │
VIX mock instruments (:8101–8103)                             │
                                                              │
OpenClaw (:18789, loopback) ◄── stdio ── FastMCP (mcp_server/, spawned from .openclaw/mcp.json)
    │
    └── AGENT.md (system prompt) + Ollama (chat model, host :11434)
```

The FastMCP server is **not** exposed on port 8001 in normal operation. OpenClaw spawns `mcp_server/server.py` as a child process over stdio when you run `openclaw` from the repo root.

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | 24+ | Backend, RAG, and VIX services |
| Python | 3.10+ | MCP server (runs outside Docker, spawned by OpenClaw) |
| OpenClaw | latest | NVIDIA agentic CLI — spawns the MCP server |
| Ollama | latest | Chat model for the agent; embeddings for RAG |

> **Note:** `docker-compose.yml` builds a `rag` service from `./rag`. That directory is not in the repo yet — `docker compose up` will fail until the RAG module is added or the compose file is adjusted. The backend and MCP tools degrade gracefully when RAG is down (empty search results).

## Setup (DGX Spark)

### 1. Clone the repo

```bash
git clone https://github.com/besaliu/LabMind.git ~/LabMind
cd ~/LabMind
```

### 2. Create required path symlinks

The MCP server runs **outside Docker** (OpenClaw spawns it directly) and expects two absolute paths. Create symlinks so Docker containers and the MCP server see the same data:

```bash
sudo ln -s ~/LabMind/labmind-data /labmind-data
sudo ln -s ~/LabMind/instruments /instruments
```

Verify:

```bash
ls /labmind-data/experiments    # should list run_001, run_002
ls /instruments/catalog         # should list temp_controller.yaml, etc.
```

### 3. Pull the model

Pull a model that fits your GPU. The setup below uses a 49B Nemotron tag; adjust if you use a different Ollama model:

```bash
ollama pull nemotron-super-49b
ollama run nemotron-super-49b "Hello"
```

Configure OpenClaw/NemoClaw inference to use the **same Ollama tag** you pulled (during onboarding choose **Local Ollama**, or at runtime: `openshell inference set --provider ollama --model nemotron-super-49b`). The repo does not pin the model in `.openclaw/` — only MCP and sandbox settings live there.

RAG embeddings also use host Ollama (`OLLAMA_HOST=http://host.docker.internal:11434` in `docker-compose.yml`) once the `rag` service exists.

### 4. Install MCP server dependencies

```bash
pip install -r mcp_server/requirements.txt
python3 --version   # must be 3.10+
```

### 5. Start backend services

```bash
docker compose up -d
docker compose ps   # backend should show "healthy"
```

| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8000 | FastAPI — experiment upload, state, analytics |
| `rag` | 8002 | Vector search over past experiments (when `./rag` is present) |
| `vix-temp-controller` | 8101 | Mock temperature controller |
| `vix-ph-probe` | 8102 | Mock pH probe |
| `vix-microscopy-imager` | 8103 | Mock microscopy imager |

### 6. Start OpenClaw

From the repo root:

```bash
openclaw
```

OpenClaw reads `.openclaw/mcp.json` and spawns the MCP server automatically. It loads `AGENT.md` as the agent system prompt. Sandbox rules are in `.openclaw/sandbox.yaml`.

Expected greeting:

```
LabMind online. RAG database contains N past experiments.
Monitoring for pending runs. Ask me anything.
```

If tools do not appear, register the same server manually (`openclaw mcp set`) using the `command`, `args`, `cwd`, and `env` from `.openclaw/mcp.json`.

### 7. Access the UI

**Experiment upload** (built into the backend):

```
http://localhost:8000
```

Or from another machine on Tailscale: `http://<spark-tailscale-ip>:8000`

**OpenClaw chat UI** binds to `127.0.0.1:18789`. Tunnel from your laptop:

```bash
ssh -N -L 18789:127.0.0.1:18789 asus@<spark-tailscale-ip>
```

Then open `http://localhost:18789`.

## Demo

### Query seed data (no upload)

- `run_001` — KDP crystal growth, slow cooling, success
- `run_002` — KDP crystal growth, fast cooling, temperature spike, partial failure

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
3. The agent detects the pending run, runs a RAG similarity check, and either asks for confirmation in chat (similarity ≥ 0.85) or registers instruments and enters monitoring mode

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
├── .openclaw/
│   ├── mcp.json             # MCP server spawn config (stdio)
│   └── sandbox.yaml         # Filesystem and network sandbox rules
├── backend/                 # FastAPI backend
├── mcp_server/              # FastMCP server (spawned by OpenClaw)
├── vix/                     # Mock instrument servers + demo_controller.py
├── instruments/catalog/     # Instrument YAML tool definitions
└── labmind-data/
    ├── experiments/         # One directory per run (seed: run_001, run_002)
    ├── instruments/         # registry.json
    └── chromadb/            # ChromaDB persistence (created by RAG service)
```

On the Spark host, `labmind-data/` and `instruments/` are also symlinked to `/labmind-data` and `/instruments` for the MCP server.

### Data layout (per run)

```
labmind-data/experiments/run_XXX/
  metadata.json         # parameters, thresholds, status, outcome
  temp.csv              # temperature (backend)
  impurity.csv          # impurity + pH (backend)
  interventions.json    # agent audit trail (MCP log_intervention)
  report.md             # morning report (finalize_experiment MCP tool)
  microscope.png        # latest image (backend)
state.json              # active_run_id, pending_run_id
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LABMIND_DATA` | `/labmind-data` | Root data directory |
| `CATALOG_DIR` | `/instruments/catalog` | Instrument YAML catalog |
| `BACKEND_URL` | `http://localhost:8000` | FastAPI URL (MCP server) |
| `RAG_SERVICE_URL` | `http://localhost:8002` | RAG service URL (MCP server) |

Defaults are set in `.openclaw/mcp.json` and `docker-compose.yml`. The 0.85 RAG similarity block threshold is currently enforced in the agent prompt (`AGENT.md`), not as a runtime config.

## Troubleshooting

**Agent says RAG is unavailable**

- `docker compose ps` — `rag` must be running (requires `./rag` to exist)
- `docker compose logs rag`

**Dynamic instrument tools missing**

- Symlink: `/instruments` → `~/LabMind/instruments`
- Catalog YAMLs in `/instruments/catalog/` (see `SCHEMAS.md`)

**Backend returns 409 on upload**

- An experiment is already active. Check `cat /labmind-data/state.json`.

**VIX instruments not registering**

- `docker compose logs vix-temp-controller`
- `curl http://localhost:8000/health`

**MCP server cannot read experiment data**

- `ls /labmind-data/experiments` must list run directories
- `LABMIND_DATA` in `.openclaw/mcp.json`

## Data schemas

All shared file formats: [SCHEMAS.md](SCHEMAS.md).

## GitHub issues

- [#1](https://github.com/besaliu/LabMind/issues/1) Parent PRD
- [#3](https://github.com/besaliu/LabMind/issues/3) FastAPI backend
- [#4](https://github.com/besaliu/LabMind/issues/4) FastMCP server
- [#5](https://github.com/besaliu/LabMind/issues/5) RAG database
- [#6](https://github.com/besaliu/LabMind/issues/6) VIX mock instruments
- [#8](https://github.com/besaliu/LabMind/issues/8) OpenClaw agent configuration
- [#9](https://github.com/besaliu/LabMind/issues/9) E2E integration + demo
