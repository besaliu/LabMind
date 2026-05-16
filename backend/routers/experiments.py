import json
import os
import httpx
import yaml
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse

from models import FinalizePayload
import storage

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8002")


# ---------------------------------------------------------------------------
# Upload experiment doc — triggers RAG similarity check
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_experiment(doc: UploadFile = File(...)):
    if storage.get_active_run_id():
        raise HTTPException(status_code=409, detail="An experiment is already active. Finalize it before starting a new one.")

    content = (await doc.read()).decode()
    parsed = _parse_doc(content, doc.filename or "")

    run_id = storage.next_run_id()
    storage.ensure_run_dir(run_id)
    meta = {
        "run_id": run_id,
        "hypothesis": parsed.get("hypothesis", ""),
        "instruments": parsed.get("instruments", []),
        "parameters": parsed.get("parameters", {}),
        "thresholds": parsed.get("thresholds", {}),
        "success_criteria": parsed.get("success_criteria", ""),
        "start_time": None,
        "end_time": None,
        "status": "pending",
        "outcome": None,
        "key_findings": [],
    }
    storage.write_metadata(run_id, meta)

    rag_findings = await _check_rag(parsed.get("hypothesis", ""), content)
    status = "blocked" if rag_findings else "clear"

    return {"run_id": run_id, "rag_findings": rag_findings, "status": status}


# ---------------------------------------------------------------------------
# Confirm — researcher proceeds after RAG block (or immediately if clear)
# ---------------------------------------------------------------------------

@router.post("/{run_id}/confirm")
def confirm_experiment(run_id: str):
    _assert_run_exists(run_id)
    meta = storage.read_metadata(run_id)

    if meta["status"] not in ("pending",):
        raise HTTPException(status_code=409, detail=f"Cannot confirm experiment in status '{meta['status']}'")

    meta["status"] = "active"
    meta["start_time"] = datetime.now(timezone.utc).isoformat()
    storage.write_metadata(run_id, meta)
    storage.set_active_run_id(run_id)

    return {"ok": True, "status": "active", "run_id": run_id}


# ---------------------------------------------------------------------------
# Current — active experiment state + latest readings
# ---------------------------------------------------------------------------

@router.get("/current")
def get_current():
    run_id = storage.get_active_run_id()
    if not run_id:
        return {"active": False}

    meta = storage.read_metadata(run_id)
    temp_rows = storage.read_csv_rows(run_id, "temp.csv")
    impurity_rows = storage.read_csv_rows(run_id, "impurity.csv")
    interventions = storage.read_interventions(run_id)

    return {
        "active": True,
        "run_id": run_id,
        "metadata": meta,
        "latest_temp": temp_rows[-1] if temp_rows else None,
        "latest_impurity": impurity_rows[-1] if impurity_rows else None,
        "intervention_count": len(interventions),
        "recent_interventions": interventions[-3:],
    }


# ---------------------------------------------------------------------------
# Report — morning summary markdown
# ---------------------------------------------------------------------------

@router.get("/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str):
    _assert_run_exists(run_id)
    path = storage.run_dir(run_id) / "report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not yet generated for this run")
    return path.read_text()


# ---------------------------------------------------------------------------
# Finalize — MCP tool calls this after writing report.md and updating metadata
# ---------------------------------------------------------------------------

@router.post("/{run_id}/finalize")
async def finalize_experiment(run_id: str, payload: FinalizePayload):
    _assert_run_exists(run_id)
    meta = storage.read_metadata(run_id)

    if meta["status"] == "completed":
        raise HTTPException(status_code=409, detail="Experiment already finalized")

    report_path = storage.run_dir(run_id) / "report.md"
    if not report_path.exists():
        raise HTTPException(status_code=422, detail="report.md not found — MCP finalize_experiment tool must write it before calling this endpoint")

    # Update metadata with finalization fields
    meta["status"] = "completed"
    meta["end_time"] = datetime.now(timezone.utc).isoformat()
    meta["outcome"] = payload.outcome
    meta["key_findings"] = payload.key_findings
    storage.write_metadata(run_id, meta)
    storage.set_active_run_id(None)

    ingested = await _trigger_rag_ingest(run_id)

    return {"ok": True, "ingested": ingested, "run_id": run_id}


# ---------------------------------------------------------------------------
# List past runs
# ---------------------------------------------------------------------------

@router.get("")
def list_experiments():
    runs = []
    for run_id in storage.list_run_ids():
        try:
            meta = storage.read_metadata(run_id)
            runs.append({
                "run_id": run_id,
                "hypothesis": meta.get("hypothesis", ""),
                "status": meta.get("status"),
                "outcome": meta.get("outcome"),
                "start_time": meta.get("start_time"),
            })
        except Exception:
            pass
    return runs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_run_exists(run_id: str) -> None:
    if not (storage.run_dir(run_id) / "metadata.json").exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


def _parse_doc(content: str, filename: str) -> dict:
    if filename.endswith((".yaml", ".yml")):
        try:
            return yaml.safe_load(content) or {}
        except yaml.YAMLError:
            pass
    # Fallback: try YAML parse on markdown frontmatter or bare YAML content
    try:
        return yaml.safe_load(content) or {}
    except Exception:
        return {"hypothesis": content[:500]}


async def _check_rag(hypothesis: str, full_text: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/query",
                json={"query": hypothesis or full_text, "top_k": 3},
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
    except Exception:
        pass
    return []


async def _trigger_rag_ingest(run_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{RAG_SERVICE_URL}/ingest", json={"run_id": run_id})
            return resp.status_code == 200
    except Exception:
        return False
