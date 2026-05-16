"""Bootstrap: ingest any finalized run on disk that isn't already in ChromaDB.

Runs at server startup (called from server.py lifespan) AND can be invoked
as a CLI: `python -m rag.seed`.

This is the self-healing mechanism that makes async finalization-ingest
(Z2) safe: if a background ingest fails or the rag service was down when
an experiment finished, the next boot picks the run back up.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from rag.api import INGESTIBLE_STATUSES, get_store, ingest_experiment

logger = logging.getLogger(__name__)

DEFAULT_DATA_ROOT = "/labmind-data"


def seed_unindexed(data_root: str | None = None) -> dict[str, list[str]]:
    """Walk experiments/ and ingest any finalized run not in the collection.

    Returns a report dict: {"ingested": [run_ids], "skipped": [run_ids], "failed": [run_ids]}.
    """
    root = Path(data_root or os.getenv("LABMIND_DATA") or DEFAULT_DATA_ROOT)
    experiments_dir = root / "experiments"
    report: dict[str, list[str]] = {"ingested": [], "skipped": [], "failed": []}

    if not experiments_dir.is_dir():
        logger.warning("experiments dir missing: %s", experiments_dir)
        return report

    existing = get_store().existing_ids()

    for run_dir in sorted(experiments_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        if run_id in existing:
            report["skipped"].append(run_id)
            continue
        if not _is_finalized(run_dir / "metadata.json"):
            report["skipped"].append(run_id)
            continue
        try:
            ingest_experiment(run_id, data_root=str(root))
            report["ingested"].append(run_id)
        except Exception as e:  # noqa: BLE001 — log and continue, don't crash startup
            logger.exception("seed: failed to ingest %s: %s", run_id, e)
            report["failed"].append(run_id)

    logger.info(
        "seed complete: ingested=%d skipped=%d failed=%d",
        len(report["ingested"]),
        len(report["skipped"]),
        len(report["failed"]),
    )
    return report


def _is_finalized(metadata_path: Path) -> bool:
    if not metadata_path.exists():
        return False
    try:
        with metadata_path.open() as f:
            md = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    return md.get("status") in INGESTIBLE_STATUSES


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = seed_unindexed()
    print(json.dumps(result, indent=2))
