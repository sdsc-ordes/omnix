"""Table and column names for the experiment hierarchy in SLIMS instance.

Everything instance-specific lives here so a rename is a one-line fix instead of
across modules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    """A SLIMS table and the columns we traverse it by."""

    table: str
    pk: str
    parent_fk: str | None = None
    name: str | None = None


# Project -> Experiment -> Run -> RunStep -> (link) -> Content ---

PROJECT = TableSpec(
    table="Project",
    pk="prjc_pk",
    name="prjc_name")

EXPERIMENT = TableSpec(
    table="Experiment",
    pk="xprm_pk",
    parent_fk="xprm_fk_project",
    name="xprm_name",
)

EXPERIMENT_RUN = TableSpec(
    table="ExperimentRun",
    pk="xprn_pk",
    parent_fk="xprn_fk_experiment",
    name="xprn_name",
)

EXPERIMENT_RUN_STEP = TableSpec(
    table="ExperimentRunStep",
    pk="xprs_pk",
    parent_fk="xprs_fk_experimentRun",
    name="xprs_name",
)

# The join table: one row per (run step, content) pair.
RUN_STEP_CONTENT = TableSpec(
    table="ExperimentRunStepContent",
    pk="xrsc_pk",
    parent_fk="xrsc_fk_experimentRunStep",
)
RUN_STEP_CONTENT_FK_CONTENT = "xrsc_fk_content"

CONTENT = TableSpec(
    table="Content",
    pk="cntn_pk",
    name="cntp_name",
)


# --- deep links --------------------------------------------------------------
def _link(base_url: str, route: str, pk: int) -> str:
    return f"{base_url.rstrip('/')}/#/{route}/{pk}"


def content_link(base_url: str, pk: int) -> str:
    return _link(base_url, "Content", pk)


def experiment_link(base_url: str, pk: int) -> str:
    return _link(base_url, "Experiment", pk)


def run_link(base_url: str, pk: int) -> str:
    return _link(base_url, "ExperimentRun", pk)


def runstep_link(base_url: str, pk: int) -> str:
    return _link(base_url, "ExperimentRunStep", pk)
