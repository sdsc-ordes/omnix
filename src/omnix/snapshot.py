"""ETL: extract from SLIMS, transform to models, write the SQLite snapshot.

This is the only part of the app that talks to SLIMS (connect to its VPN first
if it requires one). ``omnix serve`` only reads the resulting file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import extract, store, transform
from .client import connect, load_config


def run(db_path: Path | str = store.DEFAULT_DB, limit: int | None = None) -> dict[str, int]:
    """Build a fresh snapshot. `limit` caps rows per content type (dev use)."""
    config = load_config()
    slims = connect(config)

    tumor_recs = extract.fetch_all(slims, extract.TUMOR_TYPE, limit=limit)
    mouse_recs = extract.fetch_all(slims, extract.MOUSE_TYPE, limit=limit)
    treatment_recs = extract.fetch_all(slims, extract.TREATMENT_TYPE, limit=limit)
    assay_recs: list[Any] = []
    for pk in extract.ASSAY_TYPES.values():
        assay_recs += extract.fetch_all(slims, pk, limit=limit)

    treatment_lookup = transform.build_treatment_lookup(treatment_recs)

    tumors = [transform.to_tumor(r) for r in tumor_recs]
    mice = [transform.to_mouse(r, treatment_lookup) for r in mouse_recs]
    assays = [transform.to_assay(r) for r in assay_recs]

    transform.derive_tumor_fields(tumors, mice, assays)

    raw_by_id: dict[str, dict] = {}
    for rec in (*tumor_recs, *mouse_recs, *assay_recs):
        dumped = transform.raw_dump(rec)
        sid = dumped.get("cntn_id") or str(rec.pk())
        raw_by_id[str(sid)] = dumped

    conn = store.connect(db_path, read_only=False)
    try:
        _reset(conn)
        store.write_snapshot(conn, tumors, mice, assays, config["SLIMS_URL"], raw_by_id)
    finally:
        conn.close()

    return {"tumor": len(tumors), "mouse": len(mice), "assay": len(assays)}


def _reset(conn) -> None:
    """Drop existing tables so a re-run produces a clean snapshot."""
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")]
    for name in names:
        if name.startswith("sqlite_"):
            continue
        conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.commit()
