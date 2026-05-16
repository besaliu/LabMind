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

OpenClaw (:18789, loopback) ◄── stdio ── FastMCP (mcp_server/, spawned from .openclaw/mcp.json)
    │
    └── AGENT.md (system prompt) + Ollama (chat model, host :11434)
```

The FastMCP server is **not** exposed on port 8001 in normal operation. OpenClaw spawns `mcp_server/server.py` as a child process over stdio when you run `openclaw` from the repo root.

## Prerequisites

All of these must be installed and working on the Spark host before you start the setup steps.

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | 24+ | Backend and VIX services |
| Python | 3.10+ | MCP server (runs outside Docker, spawned by OpenClaw) |
| OpenClaw | latest | NVIDIA agentic CLI — spawns the MCP server |
| Ollama | latest | Chat model for the agent |
| Tailscale | latest | Required only if you want to reach the Spark from another machine |

Quick prerequisite check on the Spark:

```bash
docker --version && docker compose version
python3 --version            # must be 3.10+
ollama --version
openclaw --version           # or `which openclaw`
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

### 2. Create required path symlinks

The MCP server runs **outside Docker** (OpenClaw spawns it directly) and expects two absolute paths. Create symlinks so Docker containers and the MCP server see the same data:

```bash
sudo ln -s ~/LabMind/labmind-data /labmind-data
sudo ln -s ~/LabMind/instruments /instruments
```

Verify:

```bash
ls /labmind-data/experiments    # should list run_001, run_002
ls /instruments/catalog         # should list temp_controller.yaml, ph_probe.yaml, microscopy_imager.yaml
```

If you cannot create symlinks under `/` (some hardened systems block this even with `sudo`), the fallback is to edit `.openclaw/mcp.json` and `docker-compose.yml` to point at the repo-relative paths instead:

- In `.openclaw/mcp.json`, set `LABMIND_DATA` and `CATALOG_DIR` to absolute paths inside your clone (e.g. `/home/<user>/LabMind/labmind-data`).
- In `docker-compose.yml`, the volume mounts (`./labmind-data:/labmind-data` and `./instruments:/instruments`) already use repo-relative paths and need no change.

### 3. Pull the chat model

```bash
# Chat model — should already exist if your Spark was pre-provisioned
ollama list | grep nemotron-3-super         # confirm it's present
# If it's missing, pull it (this is large — 86 GB):
ollama pull nemotron-3-super:latest
ollama run nemotron-3-super:latest "Hello"
```

Configure OpenClaw/Nemoclaw inference to use the chat-model tag (during onboarding choose **Local Ollama**, or at runtime: `openshell inference set --provider ollama --model nemotron-3-super:latest`). The repo does not pin the model in `.openclaw/` — only MCP and sandbox settings live there.

### 4. Install MCP server dependencies

```bash
pip install -r mcp_server/requirements.txt
python3 --version   # must be 3.10+
```

### 5. Start backend services

```bash
docker compose up -d --build
docker compose ps           # all four services should be "running"; backend should be "healthy"
```

| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8000 | FastAPI — experiment upload, state, analytics |
| `vix-temp-controller` | 8101 | Mock temperature controller |
| `vix-ph-probe` | 8102 | Mock pH probe |
| `vix-microscopy-imager` | 8103 | Mock microscopy imager |

Smoke checks:

```bash
curl -s http://localhost:8000/health                       # {"status":"ok"}
curl -s http://localhost:8000/api/instruments | head -c 200 # should list the three vix instruments after ~30s
```

### 6. Start OpenClaw

From the repo root:

```bash
openclaw
```

OpenClaw reads `.openclaw/mcp.json` and spawns the MCP server automatically. It loads `AGENT.md` as the agent system prompt. Sandbox rules are in `.openclaw/sandbox.yaml`.

Confirm the MCP tools are loaded by asking the agent in the chat: "List your available MCP tools." You should see `get_experiment`, `list_experiment_reports`, `get_temperature_curve`, `compare_runs`, `log_intervention`, `finalize_experiment`, plus dynamic instrument tools like `temp_controller_read_temperature`, `ph_probe_add_buffer`, `microscopy_imager_capture_image`, etc.

If those tools do not appear, register the MCP server manually:

```bash
openclaw mcp set
# use the command, args, cwd, and env values from .openclaw/mcp.json
```

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
├── mcp_server/              # FastMCP server (spawned by OpenClaw, stdio)
├── vix/                     # Mock instrument servers (8101-8103) + demo_controller.py
├── instruments/catalog/     # Instrument YAML tool definitions (agent-writable)
├── docs/                    # Plans, handoffs, design notes
└── labmind-data/
    ├── experiments/         # One directory per run (seed: run_001, run_002)
    └── instruments/         # registry.json
```

On the Spark host, `labmind-data/` and `instruments/` are also symlinked to `/labmind-data` and `/instruments` for the MCP server.

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
| `LABMIND_DATA` | `/labmind-data` | Root data directory |
| `CATALOG_DIR` | `/instruments/catalog` | Instrument YAML catalog |
| `BACKEND_URL` | `http://localhost:8000` | FastAPI URL (MCP server) |

Defaults are set in `.openclaw/mcp.json` and `docker-compose.yml`.

## Troubleshooting

**Dynamic instrument tools missing in OpenClaw**

- Symlink check: `ls -l /instruments` must point to `~/LabMind/instruments`.
- Catalog files: `ls /instruments/catalog/` must list the three shipped YAMLs.
- Restart OpenClaw — the MCP server only spawns at OpenClaw startup, but the file watcher does pick up YAML changes within ~2s while running.

**Backend returns 409 on upload**

- An experiment is already active. Check `cat /labmind-data/state.json`; if you want to abandon it, edit `state.json` to set `"active_run_id": null` and update the run's `metadata.json` `status` to `"completed"` or delete the run directory.

**VIX instruments not registering**

- `docker compose logs vix-temp-controller` (and the other two).
- `curl http://localhost:8000/api/instruments` should list all three within 30s of `docker compose up`.

**MCP server cannot read experiment data**

- `ls /labmind-data/experiments` must list run directories — if it errors, the symlink from Step 2 is missing.
- Confirm `LABMIND_DATA` and `CATALOG_DIR` in `.openclaw/mcp.json` match the symlink targets.

**Form uploader rejects `.md` files**

- Make sure you have the latest backend image; the upload form's `accept` filter must include `.md`. If not, rebuild: `docker compose up -d --build backend`.

## Known limitations

These are documented gaps in the current implementation — they will not "just work" in the demo and require either manual intervention or pending feature work. Full detail and implementation plans in [docs/superpowers/plans/2026-05-16-feature-gaps-handoff.md](docs/superpowers/plans/2026-05-16-feature-gaps-handoff.md).

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
