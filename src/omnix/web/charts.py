"""Aggregation for the dashboard summary panel. Pure functions over a
read-only SQLite connection."""

from __future__ import annotations

import sqlite3
from typing import Any


def _breakdown(conn: sqlite3.Connection, entity: str, col: str, top: int = 8) -> list[tuple[str, int]]:
    rows = conn.execute(
        f"SELECT {col} k, COUNT(*) n FROM {entity} "
        f"WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col} ORDER BY n DESC LIMIT ?",
        (top,),
    ).fetchall()
    return [(r["k"], r["n"]) for r in rows]


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counts + small breakdowns for the dashboard / stats panel."""
    tumor_total = conn.execute("SELECT COUNT(*) FROM tumor").fetchone()[0]
    rna = conn.execute("SELECT COUNT(*) FROM tumor WHERE rna_sequenced = 1").fetchone()[0]
    return {
        "tumor_types": _breakdown(conn, "tumor", "tumor_type"),
        "mouse_generations": _breakdown(conn, "mouse", "generation"),
        "assay_types": _breakdown(conn, "assay", "assay_type"),
        "rna_sequenced": (rna, tumor_total),
    }
