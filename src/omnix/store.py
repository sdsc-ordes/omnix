"""SQLite snapshot store: schema, writer, and read queries for the web app.

Uses only the stdlib ``sqlite3``. The snapshot is a plain file (default
``.omnix/snapshot.db``); ``omnix serve`` opens it read-only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from . import content_types

DEFAULT_DB = Path(".omnix/snapshot.db")



_CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment (
    pk INTEGER PRIMARY KEY,
    project_pk INTEGER,
    name TEXT,
    omerolink TEXT,
    guid TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS exp_run (
    pk INTEGER PRIMARY KEY,
    experiment_pk INTEGER,
    name TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS exp_runstep (
    pk INTEGER PRIMARY KEY,
    exp_run_pk INTEGER,
    experiment_pk INTEGER,
    name TEXT,
    sequence INTEGER,
    raw_json TEXT
);

-- The project-to-content link with provenance path.
CREATE TABLE IF NOT EXISTS runstep_content (
    runstep_content_pk INTEGER PRIMARY KEY,
    runstep_pk INTEGER NOT NULL,
    exp_run_pk INTEGER,
    experiment_pk INTEGER,
    content_pk INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_meta (
    source_url TEXT,
    project_pk INTEGER,
    project_name TEXT,
    counts_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_exp_project    ON experiment(project_pk);
CREATE INDEX IF NOT EXISTS idx_run_experiment ON exp_run(experiment_pk);
CREATE INDEX IF NOT EXISTS idx_step_run       ON exp_runstep(exp_run_pk);
CREATE INDEX IF NOT EXISTS idx_step_exp       ON exp_runstep(experiment_pk);
CREATE UNIQUE INDEX IF NOT EXISTS idx_link_pair ON runstep_content(runstep_pk, content_pk);
CREATE INDEX IF NOT EXISTS idx_link_content    ON runstep_content(content_pk);
CREATE INDEX IF NOT EXISTS idx_link_exp        ON runstep_content(experiment_pk);
CREATE INDEX IF NOT EXISTS idx_link_run        ON runstep_content(exp_run_pk);
"""


_PROVENANCE_VIEW = """
CREATE VIEW IF NOT EXISTS content_provenance AS
SELECT
    c.pk            AS content_pk,
    c.slims_id      AS slims_id,
    c.content_type  AS content_type,
    l.runstep_pk    AS runstep_pk,
    s.name          AS runstep_name,
    l.exp_run_pk    AS exp_run_pk,
    r.name          AS exp_run_name,
    l.experiment_pk AS experiment_pk,
    e.name          AS experiment_name
FROM runstep_content l
LEFT JOIN content     c ON c.pk = l.content_pk
LEFT JOIN exp_runstep s ON s.pk = l.runstep_pk
LEFT JOIN exp_run     r ON r.pk = l.exp_run_pk
LEFT JOIN experiment  e ON e.pk = l.experiment_pk;
"""


_LINK_TABLE = """
CREATE TABLE content_to_experiment AS
-- tumors: the experiment is named after the mammoid
SELECT c.pk AS content_pk, e.pk AS experiment_pk, 'mammoid' AS via
FROM content c
JOIN experiment e ON TRIM(e.name) = TRIM(c.mammoid) COLLATE NOCASE
WHERE c.content_type IN ({tumor_types})
  AND c.mammoid IS NOT NULL AND TRIM(c.mammoid) <> ''

UNION

-- everything else: provenance through run -> runstep -> runstep content
SELECT l.content_pk, l.experiment_pk, 'runstep'
FROM runstep_content l
JOIN content c ON c.pk = l.content_pk
WHERE l.experiment_pk IS NOT NULL
  AND c.content_type NOT IN ({tumor_types});

CREATE UNIQUE INDEX idx_ce_pair ON content_to_experiment(content_pk, experiment_pk);
CREATE INDEX idx_ce_exp ON content_to_experiment(experiment_pk);
"""


def _content_schema() -> str:
    cols = ",\n    ".join(f"{c} TEXT" for c in content_types.PROMOTED_CONTENT_COLUMNS)
    idx = "\n".join(
        f"CREATE INDEX IF NOT EXISTS idx_content_{c} ON content({c});"
        for c in ("content_type", "slims_id", "mammoid")
        if c in content_types.PROMOTED_CONTENT_COLUMNS
    )
    return f"""
CREATE TABLE IF NOT EXISTS content (
    pk INTEGER PRIMARY KEY,
    {cols},
    raw_json TEXT
);
{idx}
"""


def _select_sql(
    kind: content_types.Kind,
) -> str:
    """Create SQL view for one Content Kind, projecting slims content table into typed columns."""

    base = [f"c.{col} AS {alias}" for alias, col in content_types.BASE_COLUMNS.items()]
    field_keys = {f.key for f in kind.fields}

    # Drop base columns if already declared in fields (e.g. slims_id)
    base = [b for b in base if b.split(" AS ")[-1] not in field_keys]
    projected = [f.sql_expr() for f in kind.fields]
    select = ",\n    ".join(base + projected)
    return (
        f"SELECT\n"
        f"    {select}\n"
        f"FROM content c\n"
        f"WHERE {kind.where_clause()};"
    )


def _drop_object(conn: sqlite3.Connection, name: str) -> None:
    """Removes any SQL object (VIEW or TABLE) with provided name.

    For backward compatibility.
    """
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    if row:
        conn.execute(f"DROP {row[0].upper()} IF EXISTS {name}")


def build_type_tables(conn: sqlite3.Connection) -> None:
    """(Re)create the tumor/mouse/assay tables over the content entries."""
    for kind in content_types.ALL_KINDS:
        _drop_object(conn, kind.view)
        conn.execute(f"CREATE TABLE {kind.view} AS {_select_sql(kind)}")
        for col in dict.fromkeys(["pk", "slims_id", *kind.filter_columns()]):
            conn.execute(f"CREATE INDEX idx_{kind.view}_{col} ON {kind.view}({col})")
    conn.commit()


def build_link_table(conn: sqlite3.Connection) -> None:
    _drop_object(conn, "content_to_experiment")
    types = ",".join("'" + t.replace("'", "''") + "'" for t in content_types.TUMOR_TYPES)
    conn.executescript(_LINK_TABLE.format(tumor_types=types))
    conn.commit()


def connect(
    db_path: Path | str = DEFAULT_DB,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    path = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_CORE_SCHEMA + _content_schema() + _PROVENANCE_VIEW)
    conn.commit()


# ------------------------------------------------------
# --- WRITING ------------------------------------------
# ------------------------------------------------------

def _insert_many(
    conn: sqlite3.Connection,
    table: str,
    rows: Sequence[dict[str, Any]],
) -> int:
    """INSERT OR REPLACE, with the column list built from the row dicts.

    All rows must share the same keys.
    """
    if not rows:
        return 0
    cols = list(rows[0])
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, rows)
    return len(rows)


def write_rows(
    conn: sqlite3.Connection,
    rows: Sequence[dict[str, Any]],
    table: str,
) -> int:
    n = _insert_many(conn, table, rows)
    conn.commit()
    return n


def write_meta(
    conn: sqlite3.Connection,
    source_url: str,
    project_pk: int | None,
    project_name: str | None,
) -> None:
    conn.execute(
        "INSERT INTO snapshot_meta (source_url, project_pk, project_name, counts_json)"
        " VALUES (?,?,?,?)",
        (
            source_url,
            project_pk,
            project_name,
            json.dumps(counts(conn)),
        ),
    )
    conn.commit()


# ------------------------------------------------------
# --- READING ------------------------------------------
# ------------------------------------------------------

def all_linked_content_pks(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT DISTINCT content_pk FROM runstep_content").fetchall()
    return set([r[0] for r in rows])


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in ("experiment", "exp_run", "exp_runstep", "runstep_content", "content"):
        try:
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            out[table] = 0

    try:
        out["tumor_only"] = conn.execute(f"SELECT COUNT(*) FROM content c "
            f"WHERE c.content_type IN {content_types.TUMOR_TYPES} "
            f"AND NOT EXISTS (SELECT 1 FROM content_experiment "
            f"ce WHERE ce.content_pk = c.pk);")
        out["exp_only"] = conn.execute("SELECT COUNT(*) FROM experiment e "
            "WHERE NOT EXISTS (SELECT 1 FROM content_experiment ce "
            "JOIN content c ON c.pk = ce.content_pk"
            f"WHERE ce.experiment_pk = e.pk AND c.content_type IN {content_types.TUMOR_TYPES});")
    except sqlite3.OperationalError:
        out["tumor_only"] = 0
        out["exp_only"] = 0
    return out


def get_meta(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        row = conn.execute(
            "SELECT * FROM snapshot_meta ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not row:
        return {}
    return {
        "source_url": row["source_url"],
        "project_pk": row["project_pk"],
        "project_name": row["project_name"],
        "counts": json.loads(row["counts_json"]),
    }



# ------------------------------------------------------
# --- TYPED-VIEW QUERIES (used by the web layer) -------
# ------------------------------------------------------


def _kind(view: str) -> content_types.Kind:
    kind = content_types.BY_VIEW.get(view)
    if kind is None:
        raise ValueError(f"unknown entity {view!r}")
    return kind


def _where(kind: content_types.Kind, filters: dict[str, str]) -> tuple[str, list]:
    allowed = set(kind.filter_columns())
    clauses, params = [], []
    for col, val in filters.items():
        if col not in allowed or val in (None, ""):
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
    """(page rows, total matching count) for a filtered typed view."""
    kind = _kind(entity)
    where, params = _where(kind, filters or {})
    total = conn.execute(f"SELECT COUNT(*) FROM {kind.view}{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM {kind.view}{where} ORDER BY slims_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return rows, total


def distinct_values(conn: sqlite3.Connection, entity: str, column: str, cap: int = 2000) -> list[str]:
    """Sorted distinct values for a filter column, or [] if too many (caller
    then renders a free-text input instead of a dropdown)."""
    kind = _kind(entity)
    if column not in kind.filter_columns():
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {column} v FROM {kind.view} "
        "WHERE v IS NOT NULL AND v != '' ORDER BY v LIMIT ?",
        (cap + 1,),
    ).fetchall()
    if len(rows) > cap:
        return []
    return [str(r["v"]) for r in rows]


def get_content(conn: sqlite3.Connection, content_pk: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM content WHERE pk = ?", (content_pk,)).fetchone()


def get_one_in_view(conn: sqlite3.Connection, entity: str, content_pk: int) -> sqlite3.Row | None:
    kind = _kind(entity)
    return conn.execute(f"SELECT * FROM {kind.view} WHERE pk = ?", (content_pk,)).fetchone()


def provenance_for_content(
    conn: sqlite3.Connection,
    content_pk: int
) -> list[sqlite3.Row]:
    """Every experiment / run / step a content record was used in."""
    return conn.execute(
        "SELECT * FROM content_provenance WHERE content_pk = ? "
        "ORDER BY experiment_name, exp_run_pk, runstep_pk",
        (content_pk,),
    ).fetchall()


def linked_by_mammoid(
    conn: sqlite3.Connection, mammoid: str | None, exclude_pk: int | None = None
) -> list[sqlite3.Row]:
    """Other content sharing a sample id -- the mammoid drill-down, now over the
    single content table. Content type tells the caller what each row is."""
    if not mammoid:
        return []
    return conn.execute(
        "SELECT pk, slims_id, content_type, mammoid FROM content "
        "WHERE mammoid = ? COLLATE NOCASE AND pk IS NOT ? ORDER BY content_type, slims_id",
        (mammoid.strip(), exclude_pk),
    ).fetchall()
