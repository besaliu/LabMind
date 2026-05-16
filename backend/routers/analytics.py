from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from models import AnalyticsPayload
import storage

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("")
def ingest_analytics(payload: AnalyticsPayload):
    run_id = storage.get_active_run_id()
    if not run_id:
        raise HTTPException(status_code=409, detail="No active experiment")

    instrument_type = _resolve_type(payload.instrument_id)

    if instrument_type == "temp_controller":
        storage.append_temp_row(run_id, payload.timestamp, payload.readings, payload.status)
    elif instrument_type in ("ph_probe", "chemical_stability"):
        storage.append_impurity_row(run_id, payload.timestamp, payload.readings, payload.status)
    elif instrument_type == "microscopy_imager":
        # Always write quality metrics to microscopy.csv
        storage.append_microscopy_row(run_id, payload.timestamp, payload.readings, payload.status)
        # Save image when capture_image was triggered (image_b64 present)
        import base64
        b64 = payload.readings.get("image_b64")
        if b64:
            storage.save_microscopy_image(run_id, base64.b64decode(b64))
    else:
        # Unknown type — write raw row to a catch-all JSONL file
        _append_extra(run_id, payload)

    # Touch last_seen in registry
    registry = storage.read_registry()
    if payload.instrument_id in registry:
        registry[payload.instrument_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
        storage.write_registry(registry)

    return {"ok": True}


def _resolve_type(instrument_id: str) -> str:
    """Derive instrument type from the id prefix (e.g. 'temp_controller_01' → 'temp_controller')."""
    registry = storage.read_registry()
    if instrument_id in registry:
        return registry[instrument_id]["type"]
    # Fallback: strip trailing _NN
    parts = instrument_id.rsplit("_", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else instrument_id


def _append_extra(run_id: str, payload: AnalyticsPayload) -> None:
    import json
    path = storage.run_dir(run_id) / "extra.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(payload.model_dump()) + "\n")
