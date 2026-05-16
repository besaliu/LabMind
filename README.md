# LabMind

AI lab overseer agent for air-gapped research environments. Runs locally on a DGX Spark with NemoClaw + Nemotron 3 Super 120B.

## What it does

- **Lab Assistant Mode**: Ask questions about past experiments in natural language — LabMind queries its local RAG database and responds
- **Experiment Mode**: Upload an experiment doc → agent checks for duplicate work → registers instruments → monitors overnight → detects anomalies → remediates autonomously → generates morning report → logs results to RAG

## Architecture

```
Researcher
    │
    ▼
Web Dashboard (port 5173)
    │
    ▼
FastAPI Backend (port 8000) ──── /labmind-data/ ──── FastMCP Server (port 8001)
    │                                                        │
    ▼                                                        ▼
RAG (ChromaDB)                                    OpenClaw Agent (Nemotron 120B)
    │
    ▼
VIX Mock Instruments (ports 8101–8105)
```

## Quick Start

### Prerequisites

- DGX Spark with NemoClaw installed
- Docker + Docker Compose
- Ollama running with `nemotron-super` and `nomic-embed-text` pulled

### Start all services

```bash
docker compose up
```

Services start on:

| Service | Port |
|---------|------|
| FastAPI backend | 8000 |
| FastMCP server | 8001 |
| Dashboard | 5173 |
| VIX temp controller | 8101 |
| VIX pH probe | 8102 |
| VIX microscopy imager | 8103 |

### Start the LabMind agent (NemoClaw)

```bash
nemoclaw start
```

The agent reads `AGENT.md` for instructions and `.openclaw/mcp.json` to connect to the FastMCP server.

### Run the demo

```bash
python demo/demo_controller.py
```

See `demo/README.md` for the full demo script.

## Repository Structure

```
LabMind/
├── AGENT.md                    # OpenClaw agent instructions
├── SCHEMAS.md                  # All shared data format contracts
├── .openclaw/
│   └── mcp.json               # MCP server registration
├── backend/                    # FastAPI backend (issue #3)
├── mcp_server/                 # FastMCP server (issue #4)
├── rag/                        # ChromaDB RAG module (issue #5)
├── vix/                        # Mock instrument servers (issue #6)
├── dashboard/                  # Web dashboard (issue #7)
├── instruments/
│   └── catalog/               # Instrument type YAML definitions
├── labmind-data/
│   ├── experiments/           # One directory per run
│   ├── instruments/           # registry.json
│   └── chromadb/             # ChromaDB persistence
└── demo/                      # Demo controller + scripts
```

## Data Schemas

All shared file formats are documented in [SCHEMAS.md](SCHEMAS.md).

## GitHub Issues

See the [issue tracker](https://github.com/besaliu/LabMind/issues) for module assignments:

- [#2](../../issues/2) Repo scaffold (this issue)
- [#3](../../issues/3) FastAPI Backend
- [#4](../../issues/4) FastMCP Server + dynamic tool registration
- [#5](../../issues/5) RAG Database
- [#6](../../issues/6) VIX mock instruments
- [#7](../../issues/7) Web Dashboard
- [#8](../../issues/8) OpenClaw agent configuration
- [#9](../../issues/9) E2E integration + demo rehearsal

Parent PRD: [#1](../../issues/1)
