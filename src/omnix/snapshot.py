"""ETL: extract from SLIMS, transform to models, write the SQLite snapshot.

This is the only part of the app that talks to SLIMS (connect to its VPN first
if it requires one). ``omnix serve`` only reads the resulting file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import extract, store, transform, slims_spec
from .client import connect, load_config

logger = logging.getLogger(__name__)

PROJ_NAME = "Human Primary Tumor Cells and BRCA MINDs"
PROJ_PK = 76

def run(
    db_path: Path | str = store.DEFAULT_DB,
    project_name: str = PROJ_NAME,
    project_pk: int | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Build/update a snapshot. Returns row counts per table.

    Args:
        db_path: Path to the SQLite database.
        project_name: Project name referenced in slims Project table.
        project_pk: skip the name-to-pk lookup and use this pk directly.
        limit: Limit on the number of content items to fetch (for dev).
    """
    config = load_config()
    slims = connect(config)
    base_url = config["SLIMS_URL"].replace("rest", "")

    conn = store.connect(db_path, read_only=False)
    try:
        _reset(conn)
        store.init_schema(conn)

        # Procede to build the snapshot in two phases:
        # 1. fetch all the content pks related to the project
        # 2. fetch and store the actual content
        _phase_fetch_structure(
            conn, slims, base_url, project_name, project_pk
        )
        _phase_fetch_content(conn, slims, base_url, limit=limit)
        result = store.counts(conn)
        store.build_type_views(conn)
        store.write_meta(conn, base_url, project_pk, project_name)
        return result
    finally:
        conn.close()


def _phase_fetch_structure(
    conn,
    slims,
    base_url: str,
    project_name: str,
    project_pk: int | None
) -> None:
    if project_pk is None:
        project = extract.fetch_project(slims, project_name)
        project_pk = int(project.pk())
    logger.info(f"Project {project_name!r} -> pk={project_pk}")

    # Experiments
    logger.info("Fetching experiment record(s).")
    exp_rows = []
    for batch in extract.fetch_by_parents(slims, slims_spec.EXPERIMENT, [project_pk]):
        batch_exp_rows = [transform.experiment_row(r, project_pk, base_url) for r in batch]
        if not batch_exp_rows:
            continue
        store.write_rows(conn, batch_exp_rows, "experiment")
        exp_rows.extend(batch_exp_rows)
    logger.info(f"{len(exp_rows)} experiment(s) found.")

    # Experiment runs
    logger.info("Fetching experiment run record(s) per experiment.")
    run_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.EXPERIMENT_RUN, [r["pk"] for r in exp_rows]):
        batch_run_rows = [transform.run_row(r, base_url) for r in batch]
        if not batch_run_rows:
            continue
        store.write_rows(conn, batch_run_rows, "exp_run")
        run_rows.extend(batch_run_rows)
    experiment_by_run = {r["pk"]: r["experiment_pk"] for r in run_rows}
    logger.info(f"{len(run_rows)} run(s) found.")

    # Experiment run steps
    logger.info("Fetching experiment run step record(s) per experiment run.")
    runstep_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.EXPERIMENT_RUN_STEP, list(experiment_by_run)):
        batch_runstep_rows = [transform.runstep_row(r, base_url, experiment_by_run) for r in batch]
        if not batch_runstep_rows:
            continue
        store.write_rows(conn, batch_runstep_rows, "exp_runstep")
        runstep_rows.extend(batch_runstep_rows)
    run_by_step = {r["pk"]: r["exp_run_pk"] for r in runstep_rows}
    logger.info(f"{len(runstep_rows)} run step(s) found.")

    # Experiment run step contents
    logger.info("Fetching experiment run step content record(s) per run step.")
    runstep_content_link_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.RUN_STEP_CONTENT, list(run_by_step)):

        # Keep track of the link Experiment -> ExperimentRun ... -> Content
        batch_content_link_rows = [
            row
            for row in (transform.content_link_row(r, run_by_step, experiment_by_run) for r in batch)
            if row is not None
        ]
        store.write_rows(conn, batch_content_link_rows, "runstep_content")
        runstep_content_link_rows.extend(batch_content_link_rows)
    logger.info(
        f"{len(runstep_content_link_rows)} link(s) -> "
        f"{len({r['content_pk'] for r in runstep_content_link_rows})} distinct content pk(s)",
    )


def _phase_fetch_content(
    conn,
    slims,
    base_url: str,
    limit: int | None,
) -> int:
    pks = store.all_linked_content_pks(conn)
    if not pks:
        logger.info("No content to fetch")
        return 0

    logger.info(f"Fetching {len(pks)} content record(s)")
    total = 0
    for batch in extract.fetch_content(slims, pks, limit=limit):
        rows = [transform.content_row(r, base_url) for r in batch]
        store.write_rows(conn, rows, "content")
        total += len(rows)
        logger.info(f"  {total}/{len(pks)}")

    return total


def _reset(conn) -> None:
    """Drop existing tables/views so a re-run produces a clean snapshot."""
    rows = conn.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view')").fetchall()
    for name, kind in rows:
        if name.startswith("sqlite_"):
            continue
        conn.execute(f"DROP {kind.upper()} IF EXISTS {name}")
    conn.commit()
