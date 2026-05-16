"""Read-only filesystem helpers for the MCP server.
The FastAPI backend owns writes to experiment data; the MCP server only reads,
except for finalize_experiment which writes report.md and updates metadata.json.
"""
import csv
import json
import os
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _data() -> Path:
    return Path(os.environ.get("LABMIND_DATA", "/labmind-data"))


def _experiments_dir() -> Path:
    return _data() / "experiments"


def _catalog_dir() -> Path:
    return Path(os.environ.get("CATALOG_DIR", "/instruments/catalog"))


def get_active_run_id() -> Optional[str]:
    state_file = _data() / "state.json"
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text()).get("active_run_id")


def run_dir(run_id: str) -> Path:
    return _experiments_dir() / run_id


def read_metadata(run_id: str) -> Dict[str, Any]:
    return json.loads((run_dir(run_id) / "metadata.json").read_text())


def write_metadata(run_id: str, meta: Dict[str, Any]) -> None:
    (run_dir(run_id) / "metadata.json").write_text(json.dumps(meta, indent=2))


def read_csv(run_id: str, filename: str) -> List[Dict[str, str]]:
    path = run_dir(run_id) / filename
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def read_image_b64(run_id: str) -> Optional[str]:
    path = run_dir(run_id) / "microscope.png"
    if not path.exists():
        return None
    return b64encode(path.read_bytes()).decode()


def read_interventions(run_id: str) -> List[Dict[str, Any]]:
    path = run_dir(run_id) / "interventions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def append_intervention(run_id: str, entry: Dict[str, Any]) -> None:
    interventions = read_interventions(run_id)
    interventions.append(entry)
    (run_dir(run_id) / "interventions.json").write_text(
        json.dumps(interventions, indent=2)
    )


def write_report(run_id: str, content: str) -> bool:
    path = run_dir(run_id) / "report.md"
    if path.exists():
        return False  # already written — prevent double-finalization
    path.write_text(content)
    return True


def list_catalog_yamls() -> List[Path]:
    d = _catalog_dir()
    if not d.exists():
        return []
    return list(d.glob("*.yaml")) + list(d.glob("*.yml"))
