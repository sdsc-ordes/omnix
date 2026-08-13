"""Aggregation for the dashboard. Pure functions over a read-only connection,
querying the typed views (built from the content table). View names come from
the registry, so renaming a page's slug does not break the dashboard."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import content_types


def _view(slug: str) -> str | None:
    kind = content_types.BY_SLUG.get(slug)
    return kind.view if kind else None


def _breakdown(
    conn: sqlite3.Connection, view: str | None, col: str, top: int = 8
) -> list[tuple[str, int]]:
    if not view:
        return []
    try:
        rows = conn.execute(
            f"SELECT {col} k, COUNT(*) n FROM {view} "
            f"WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col} ORDER BY n DESC LIMIT ?",
            (top,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["k"], r["n"]) for r in rows]


def _count(conn: sqlite3.Connection, view: str | None) -> int:
    if not view:
        return 0
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Per-kind counts + small breakdowns for the dashboard panel."""
    kind_counts = {k.slug: _count(conn, k.view) for k in content_types.ALL_KINDS}

    tumors_view = _view("tumors")
    tumor_total = _count(conn, tumors_view)
    rna = 0
    if tumor_total:
        try:
            rna = conn.execute(
                f"SELECT COUNT(*) FROM {tumors_view} WHERE rna_sequenced = 1"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            rna = 0

    return {
        "kind_counts": kind_counts,
        "tumor_types": _breakdown(conn, tumors_view, "tumor_type"),
        "mouse_strains": _breakdown(conn, _view("mice"), "strain"),
        "assay_types": _breakdown(conn, _view("assays"), "assay_type"),
        "rna_sequenced": (rna, tumor_total),
    }
