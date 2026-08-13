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


PROJ_PK_PER_NAME = {
    "Human Primary Tumor Cells and BRCA MINDs": 76
}


def run(
    db_path: Path | str,
    project_name: str,
    limit: int | None = None,
) -> dict[str, int]:
    """Build a snapshot. Returns row counts per table.

    Args:
        db_path: Path to the SQLite database.
        project_name: Name of the project to fetch.
        limit: Limit on the number of content items to fetch (for dev).
    """
    config = load_config()
    slims = connect(config)
    base_url = config["SLIMS_URL"]

    conn = store.connect(db_path, read_only=False)
    try:
        _reset(conn)
        store.init_schema(conn)

        # Procede to build the snapshot in two phases:
        # 1. fetch all the content pks related to the project
        # 2. fetch and store the actual content
        mammoid_set = _phase_fetch_structure(
            conn, slims, project_name, limit=limit,
        )
        _phase_fetch_content(conn, slims, mammoid_set, limit=limit)
        store.build_link_table(conn)
        store.build_type_tables(conn)
        result = store.counts(conn)
        store.write_meta(conn, base_url, project_name, result)
        return result
    finally:
        conn.close()


def _phase_fetch_structure(
    conn,
    slims,
    project_name: str,
    limit: int | None = None,
) -> set:
    """Fetch the full project structure from SLIMS for a given project name.

    The project structure is as follows: Project -> Experiment -> Experiment Run
    -> Experiment Runsteps -> Experiment Runstep Content. Each record is fetched
    and stored directly in the database.
    """
    if project_name in PROJ_PK_PER_NAME:
        project_pk = PROJ_PK_PER_NAME[project_name]
    else:
        project = extract.fetch_project(slims, project_name)
        project_pk = int(project.pk())
        logger.info(f"Project {project_name!r} -> pk={project_pk}")

    # Experiments
    logger.info("Fetching experiment record(s).")
    exp_rows = []
    mammoid_set = set()
    for batch in extract.fetch_by_parents(slims, slims_spec.EXPERIMENT, [project_pk]):
        batch_exp_rows = [transform.experiment_row(r, project_pk) for r in batch]
        store.write_rows(conn, batch_exp_rows, "experiment")
        mammoid_set.update([exp_row["name"] for exp_row in batch_exp_rows])
        exp_rows.extend(batch_exp_rows)
    logger.info(f"{len(exp_rows)} experiment(s) found.")

    # Experiment runs
    logger.info("Fetching experiment run record(s) per experiment.")
    run_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.EXPERIMENT_RUN, [r["pk"] for r in exp_rows]):
        batch_run_rows = [transform.run_row(r) for r in batch]
        store.write_rows(conn, batch_run_rows, "exp_run")
        run_rows.extend(batch_run_rows)
    experiment_by_run = {r["pk"]: r["experiment_pk"] for r in run_rows}
    logger.info(f"{len(run_rows)} run(s) found.")

    # Experiment runsteps
    logger.info("Fetching experiment run step record(s) per experiment run.")
    runstep_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.EXPERIMENT_RUN_STEP, list(experiment_by_run)):
        batch_runstep_rows = [transform.runstep_row(r, experiment_by_run) for r in batch]
        store.write_rows(conn, batch_runstep_rows, "exp_runstep")
        runstep_rows.extend(batch_runstep_rows)
    run_by_step = {r["pk"]: r["exp_run_pk"] for r in runstep_rows}
    logger.info(f"{len(runstep_rows)} run step(s) found.")

    # Experiment run step contents
    logger.info("Fetching experiment run step content record(s) per run step.")
    runstep_content_link_rows = []
    for batch in extract.fetch_by_parents(
        slims, slims_spec.RUN_STEP_CONTENT, list(run_by_step), limit=limit):

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
    return mammoid_set


def _phase_fetch_content(
    conn,
    slims,
    mammoid_set,
    limit: int | None,
) -> None:
    """Fetch Tumor, Mouse, Assays content in two passes.

    First fetch tumor using mammoids. The mammoids is assumed to correspond
    to experiment name. Then fetch all remaining content types by pks. No duplicate.
    """
    total = 0
    fetched_pks : set[int] = set()
    if len(mammoid_set) != 0:
        logger.info(f"Fetching {len(mammoid_set)} Tumor content record(s) by mammoid")
        for batch in extract.fetch_content_by_mammoid(slims, mammoid_set, limit=limit):
            rows = [transform.content_row(r) for r in batch]
            fetched_pks.update([row["pk"] for row in rows])
            store.write_rows(conn, rows, "content")
            total += len(rows)
            logger.info(f"  {total}/{len(mammoid_set)}")

    pks = store.all_linked_content_pks(conn)
    pks -= fetched_pks
    if not pks:
        logger.info("No remaining content to fetch by pk.")
        return

    logger.info(f"Fetching {len(pks)} Mouse/Assays content record(s) using pk"
        " from linked experiment record")
    total = 0
    for batch in extract.fetch_content_by_pk(slims, pks, limit=limit):
        rows = [transform.content_row(r) for r in batch]
        store.write_rows(conn, rows, "content")
        total += len(rows)
        logger.info(f"  {total}/{len(pks)}")


def _reset(conn) -> None:
    """Drop existing tables/views so a re-run produces a clean snapshot."""
    rows = conn.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view')").fetchall()
    for name, kind in rows:
        if name.startswith("sqlite_"):
            continue
        conn.execute(f"DROP {kind.upper()} IF EXISTS {name}")
    conn.commit()
