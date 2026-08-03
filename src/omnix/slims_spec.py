"""Table and column names for the experiment hierarchy in SLIMS instance.

Everything instance-specific lives here so a rename is a one-line fix instead of
across modules.
"""

from __future__ import annotations
from dataclasses import dataclass


SLIMS_BASE_URL = "https://slims.epfl.ch/upbri/Slims.html?initialModule=eln&initialRecordGuid="


@dataclass(frozen=True)
class TableSpec:
    """A SLIMS table and the columns we traverse it by."""

    table: str
    pk: str
    parent_fk: str | None = None
    name: str | None = None
    omerolink: str | None = None
    guid: str | None = None


# Project -> Experiment -> Run -> RunStep -> RunStepContent <---> Content

PROJECT = TableSpec(
    table="Project",
    pk="prjc_pk",
    name="prjc_name")

EXPERIMENT = TableSpec(
    table="Experiment",
    pk="xprm_pk",
    parent_fk="xprm_fk_project",
    name="xprm_name",
    omerolink="xprm_cf_omeroLink",
    guid="xprm_uniqueIdentifier",
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
