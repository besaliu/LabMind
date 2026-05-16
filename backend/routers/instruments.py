from fastapi import APIRouter

from models import InstrumentRegistration
import storage

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.post("/register")
def register_instrument(payload: InstrumentRegistration):
    storage.upsert_instrument(payload.instrument_id, payload.model_dump())
    return {
        "ok": True,
        "run_id": storage.get_active_run_id(),
    }


@router.get("")
def list_instruments():
    return storage.read_registry()
