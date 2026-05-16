"""File I/O helpers. All reads/writes go through here — no direct filesystem access in routers."""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any


def _data() -> Path:
    return Path(os.environ.get("LABMIND_DATA", "/labmind-data"))


def _experiments_dir() -> Path:
    return _data() / "experiments"


def _instruments_dir() -> Path:
    return _data() / "instruments"


def _state_file() -> Path:
    return _data() / "state.json"


TEMP_CSV_HEADERS     = ["timestamp", "temperature_c", "setpoint_c", "status"]
IMPURITY_CSV_HEADERS = ["timestamp", "impurity_ppm", "saturation_pct", "ph", "status"]


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def read_state() -> Dict[str, Any]:
    f = _state_file()
    if not f.exists():
        return {"active_run_id": None}
    return json.loads(f.read_text())


def write_state(state: Dict[str, Any]) -> None:
    _state_file().write_text(json.dumps(state, indent=2))


def get_active_run_id() -> Optional[str]:
    return read_state().get("active_run_id")


def set_active_run_id(run_id: Optional[str]) -> None:
    state = read_state()
    state["active_run_id"] = run_id
    write_state(state)


# ---------------------------------------------------------------------------
# Run directory helpers
# ---------------------------------------------------------------------------

def run_dir(run_id: str) -> Path:
    return _experiments_dir() / run_id


def ensure_run_dir(run_id: str) -> Path:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_metadata(run_id: str) -> Dict[str, Any]:
    return json.loads((run_dir(run_id) / "metadata.json").read_text())


def write_metadata(run_id: str, meta: Dict[str, Any]) -> None:
    (run_dir(run_id) / "metadata.json").write_text(json.dumps(meta, indent=2))


def list_run_ids() -> List[str]:
    d = _experiments_dir()
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def next_run_id() -> str:
    nums = []
    for r in list_run_ids():
        try:
            nums.append(int(r.replace("run_", "")))
        except ValueError:
            pass
    return f"run_{max(nums, default=0) + 1:03d}"


# ---------------------------------------------------------------------------
# CSV append helpers
# ---------------------------------------------------------------------------

def _ensure_csv(path: Path, headers: List[str]) -> None:
    if not path.exists():
        with path.open("w", newline="") as f:
            csv.writer(f).writerow(headers)


def append_temp_row(run_id: str, timestamp: str, readings: Dict[str, Any], status: str) -> None:
    path = run_dir(run_id) / "temp.csv"
    _ensure_csv(path, TEMP_CSV_HEADERS)
    with path.open("a", newline="") as f:
        csv.writer(f).writerow([
            timestamp,
            readings.get("temperature_c", ""),
            readings.get("setpoint_c", ""),
            status,
        ])


def append_impurity_row(run_id: str, timestamp: str, readings: Dict[str, Any], status: str) -> None:
    path = run_dir(run_id) / "impurity.csv"
    _ensure_csv(path, IMPURITY_CSV_HEADERS)
    with path.open("a", newline="") as f:
        csv.writer(f).writerow([
            timestamp,
            readings.get("impurity_ppm", ""),
            readings.get("saturation_pct", ""),
            readings.get("ph", ""),
            status,
        ])


def save_microscopy_image(run_id: str, image_bytes: bytes) -> None:
    (run_dir(run_id) / "microscope.png").write_bytes(image_bytes)


def read_csv_rows(run_id: str, filename: str) -> List[Dict[str, str]]:
    path = run_dir(run_id) / filename
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Instrument registry helpers
# ---------------------------------------------------------------------------

def read_registry() -> Dict[str, Any]:
    path = _instruments_dir() / "registry.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_registry(registry: Dict[str, Any]) -> None:
    d = _instruments_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "registry.json").write_text(json.dumps(registry, indent=2))


def upsert_instrument(instrument_id: str, data: Dict[str, Any]) -> None:
    registry = read_registry()
    now = datetime.now(timezone.utc).isoformat()
    registry[instrument_id] = {
        **data,
        "last_seen": now,
        "status": "online",
        "registered_at": registry.get(instrument_id, {}).get("registered_at", now),
    }
    write_registry(registry)


# ---------------------------------------------------------------------------
# Interventions helpers
# ---------------------------------------------------------------------------

def read_interventions(run_id: str) -> List[Dict[str, Any]]:
    path = run_dir(run_id) / "interventions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def append_intervention(run_id: str, entry: Dict[str, Any]) -> None:
    interventions = read_interventions(run_id)
    interventions.append(entry)
    (run_dir(run_id) / "interventions.json").write_text(json.dumps(interventions, indent=2))
