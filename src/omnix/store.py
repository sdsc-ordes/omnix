"""SQLite snapshot store: schema, writer, and read queries for the web app.

Uses only the stdlib ``sqlite3``. The snapshot is a plain file (default
``.omnix/snapshot.db``); ``omnix serve`` opens it read-only. Full-text search
uses FTS5 when available, falling back to ``LIKE`` otherwise.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Assay, Mouse, Mutation, Tumor

DEFAULT_DB = Path(".omnix/snapshot.db")

# Whitelisted filter columns per entity (guards against SQL injection via names).
FILTER_COLUMNS = {
    "tumor": ["tumor_type", "subtype", "grade", "her2", "mammoid", "rna_sequenced"],
    "mouse": ["generation", "generation_mm", "strain", "sex", "project", "treatment", "mammoid"],
    "assay": ["assay_type", "organ", "mammoid"],
}

SCHEMA = """
CREATE TABLE tumor (
    slims_id TEXT PRIMARY KEY, mammoid TEXT, name TEXT, tumor_type TEXT,
    subtype TEXT, grade TEXT, er TEXT, pr TEXT, her2 TEXT, ki67 TEXT,
    rna_sequenced INTEGER, dna_sequenced INTEGER, n_experiments INTEGER,
    treatments TEXT, raw_json TEXT
);
CREATE TABLE mouse (
    slims_id TEXT PRIMARY KEY, mammoid TEXT, mouse_exp_nb TEXT, generation TEXT,
    generation_mm TEXT, treatment TEXT, mutations_raw TEXT, strain TEXT,
    sex TEXT, project TEXT, raw_json TEXT
);
CREATE TABLE assay (
    slims_id TEXT PRIMARY KEY, assay_type TEXT, mammoid TEXT, mouse_exp_nb TEXT,
    organ TEXT, original_content TEXT, raw_json TEXT
);
CREATE TABLE mutation (
    sample_kind TEXT, sample_id TEXT, gene TEXT, status TEXT
);
CREATE TABLE snapshot_meta (
    created_at TEXT, source_url TEXT, counts_json TEXT
);
CREATE INDEX idx_tumor_mammoid ON tumor(mammoid);
CREATE INDEX idx_mouse_mammoid ON mouse(mammoid);
CREATE INDEX idx_assay_mammoid ON assay(mammoid);
CREATE INDEX idx_assay_type ON assay(assay_type);
CREATE INDEX idx_tumor_type ON tumor(tumor_type);
CREATE INDEX idx_mouse_generation ON mouse(generation);
CREATE INDEX idx_mutation_sample ON mutation(sample_id);
"""


def connect(db_path: Path | str = DEFAULT_DB, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _fts_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


# --- writing -----------------------------------------------------------------


def write_snapshot(  # noqa: PLR0913 (one row per entity list + source + raw)
    conn: sqlite3.Connection,
    tumors: list[Tumor],
    mice: list[Mouse],
    assays: list[Assay],
    mutations: list[Mutation],
    source_url: str,
    raw_by_id: dict[str, dict] | None = None,
) -> None:
    raw_by_id = raw_by_id or {}
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT OR REPLACE INTO tumor VALUES "
        "(:slims_id,:mammoid,:name,:tumor_type,:subtype,:grade,:er,:pr,:her2,:ki67,"
        ":rna_sequenced,:dna_sequenced,:n_experiments,:treatments,:raw_json)",
        [
            {
                **t.model_dump(),
                "rna_sequenced": int(t.rna_sequenced),
                "dna_sequenced": int(t.dna_sequenced),
                "treatments": json.dumps(t.treatments),
                "raw_json": json.dumps(raw_by_id.get(t.slims_id, {})),
            }
            for t in tumors
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO mouse VALUES "
        "(:slims_id,:mammoid,:mouse_exp_nb,:generation,:generation_mm,:treatment,"
        ":mutations_raw,:strain,:sex,:project,:raw_json)",
        [{**m.model_dump(), "raw_json": json.dumps(raw_by_id.get(m.slims_id, {}))} for m in mice],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO assay VALUES "
        "(:slims_id,:assay_type,:mammoid,:mouse_exp_nb,:organ,:original_content,:raw_json)",
        [{**a.model_dump(), "raw_json": json.dumps(raw_by_id.get(a.slims_id, {}))} for a in assays],
    )
    conn.executemany(
        "INSERT INTO mutation VALUES (:sample_kind,:sample_id,:gene,:status)",
        [mut.model_dump() for mut in mutations],
    )

    _build_search(conn)

    counts = {
        "tumor": len(tumors),
        "mouse": len(mice),
        "assay": len(assays),
        "mutation": len(mutations),
    }
    conn.execute(
        "INSERT INTO snapshot_meta VALUES (?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), source_url, json.dumps(counts)),
    )
    conn.commit()


def _build_search(conn: sqlite3.Connection) -> None:
    """Populate a search index across the three entities' text fields."""
    rows: list[tuple[str, str, str]] = []
    for entity in ("tumor", "mouse", "assay"):
        for r in conn.execute(f"SELECT * FROM {entity}"):
            body = " ".join(
                str(v) for k, v in dict(r).items() if k != "raw_json" and v not in (None, "")
            )
            rows.append((entity, r["slims_id"], body))
    if _fts_available(conn):
        conn.execute("CREATE VIRTUAL TABLE search USING fts5(entity, slims_id, body)")
    else:
        conn.execute("CREATE TABLE search (entity TEXT, slims_id TEXT, body TEXT)")
    conn.executemany("INSERT INTO search VALUES (?,?,?)", rows)


# --- reading -----------------------------------------------------------------


def get_meta(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM snapshot_meta ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        return {}
    return {"created_at": row["created_at"], "source_url": row["source_url"], "counts": json.loads(row["counts_json"])}


def _where(entity: str, filters: dict[str, str]) -> tuple[str, list]:
    clauses, params = [], []
    for col, val in filters.items():
        if col not in FILTER_COLUMNS.get(entity, []) or val in (None, ""):
            continue
        clauses.append(f"{col} LIKE ?")
        params.append(f"%{val}%")
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def list_entity(
    conn: sqlite3.Connection,
    entity: str,
    filters: dict[str, str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[sqlite3.Row], int]:
    """Return (page rows, total matching count) for a filtered entity list."""
    if entity not in FILTER_COLUMNS:
        raise ValueError(f"unknown entity {entity!r}")
    where, params = _where(entity, filters or {})
    total = conn.execute(f"SELECT COUNT(*) FROM {entity}{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM {entity}{where} ORDER BY slims_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return rows, total


def distinct_values(conn: sqlite3.Connection, entity: str, column: str, cap: int = 40) -> list[str]:
    """Sorted distinct non-null values for a filter column, or [] if too many
    (caller then renders a free-text input instead of a dropdown)."""
    if entity not in FILTER_COLUMNS or column not in FILTER_COLUMNS[entity]:
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {column} v FROM {entity} "
        f"WHERE v IS NOT NULL AND v != '' ORDER BY v LIMIT ?",
        (cap + 1,),
    ).fetchall()
    if len(rows) > cap:
        return []
    return [str(r["v"]) for r in rows]


def get_one(conn: sqlite3.Connection, entity: str, slims_id: str) -> sqlite3.Row | None:
    if entity not in FILTER_COLUMNS:
        raise ValueError(f"unknown entity {entity!r}")
    return conn.execute(f"SELECT * FROM {entity} WHERE slims_id = ?", (slims_id,)).fetchone()


def linked_to_tumor(conn: sqlite3.Connection, mammoid: str | None) -> dict[str, list[sqlite3.Row]]:
    """Mice & assays sharing a tumor's (normalized) mammoid -- the drill-down."""
    if not mammoid:
        return {"mice": [], "assays": []}
    key = mammoid.strip()
    mice = conn.execute("SELECT * FROM mouse WHERE mammoid = ? COLLATE NOCASE", (key,)).fetchall()
    assays = conn.execute("SELECT * FROM assay WHERE mammoid = ? COLLATE NOCASE", (key,)).fetchall()
    return {"mice": mice, "assays": assays}


def search(conn: sqlite3.Connection, q: str, limit: int = 100) -> list[sqlite3.Row]:
    if not q:
        return []
    is_fts = "fts5" in (conn.execute("SELECT sql FROM sqlite_master WHERE name='search'").fetchone()[0] or "")
    if is_fts:
        return conn.execute(
            "SELECT entity, slims_id, body FROM search WHERE search MATCH ? LIMIT ?",
            (q + "*", limit),
        ).fetchall()
    return conn.execute(
        "SELECT entity, slims_id, body FROM search WHERE body LIKE ? LIMIT ?",
        (f"%{q}%", limit),
    ).fetchall()


def mutation_matrix(conn: sqlite3.Connection, sample_kind: str = "mouse") -> dict[str, Any]:
    """Genes x samples matrix for the oncoprint: {genes, samples, cells{(gene,sample):status}}."""
    rows = conn.execute(
        "SELECT sample_id, gene, status FROM mutation WHERE sample_kind = ?", (sample_kind,)
    ).fetchall()
    genes = sorted({r["gene"] for r in rows})
    samples = sorted({r["sample_id"] for r in rows})
    cells = {(r["gene"], r["sample_id"]): r["status"] for r in rows}
    return {"genes": genes, "samples": samples, "cells": cells}
