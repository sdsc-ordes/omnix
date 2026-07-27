"""Typed domain models for the xenograft export.

These mirror the target shape in ``docs/xenograft-data-model.md``. Fields are
optional wherever the underlying SLIMS custom field is sparsely populated (see
the coverage table in that doc). The raw SLIMS column dump is kept separately by
the store, not on these models -- these stay clean for JSON export.
"""

from __future__ import annotations

from pydantic import BaseModel


class Project(BaseModel):
    slims_pk: int
    name: str | None = None


class Experiment(BaseModel):
    slims_link: str
    slims_pk: int
    name: str
    protocol: str | None = None
    list_run_pks: list[int] = []
    list_runstep_pks: dict[int,list[int]] = {}
    list_runstep_content_pks: dict[int,list[int]] = {}
    project: Project | None = None


class ExpRun(BaseModel):
    slims_link: str
    slims_pk: int
    name: str
    protocol: str | None = None
    list_runstep_pks: list[int] = []
    list_runstep_content_pks: dict[int,list[int]] = {}
    project: Project | None = None
    experiment: Experiment | None = None


class ExpRunStep(BaseModel):
    slims_link: str
    slims_pk: int
    name: str
    list_runstep_content_pks: list[int] = []
    project: Project | None = None
    experiment: Experiment | None = None
    experiment_run: ExpRun | None = None


class ContentLinkChain(BaseModel):
    """One ContentLinkChain row: a Content pk attached to a run step,
    plus the chain (step -> run -> experiment) it belongs to.

    Persisted as the ``runstep_content`` table. This is the only place the
    provenance exists -- a Content record carries no back-reference to the run
    step that used it, so if this is not stored, it cannot be recovered without
    walking SLIMS again.
    """
    content_pk: int
    exp_runstep_pk: int
    exp_run_pk: int
    experiment_pk: int


class Tumor(BaseModel):
    slims_id: str
    slims_link: str
    slims_pk: int
    slims_exp_pk: int
    slims_exp_link: str
    type: str  # cntn_fk_contentType (e.g. Tumor, Mets)
    mammoid: str | None = None  # join key (cntn_cf_mammoid), clean on tumors
    name: str | None = None  # cntn_cf_Name
    tumor_type: str | None = None  # cntn_cf_Type (e.g. BRCA1)
    subtype: str | None = None  # cntn_cf_subtype
    grade: str | None = None  # cntn_cf_Grade
    er: str | None = None  # cntn_cf_erShortText
    pr: str | None = None  # cntn_cf_prShortText
    her2: str | None = None  # cntn_cf_Her2
    ki67: str | None = None  # cntn_cf_ki67ShortText

    # Derived (see transform.derive_tumor_fields):
    rna_sequenced: bool = False
    imaged: bool = False
    treated: bool = False
    n_experiments: int = 0
    n_mouse: int = 0
    treatments: list[str] = []

# or PDX?
class Mouse(BaseModel):
    slims_id: str
    slims_link: str
    slims_pk: int
    mammoid: str | None = None  # cntn_cf_mammoid (free text on mice -- unreliable join)
    experiment: str
    exp_run: str
    exp_runsteps : list[str] = []
    mouse_exp_nb: str | None = None  # cntn_cf_mouseExpNb
    treatment: str | None = None  # cntn_cf_fk_treatment (resolved label)
    strain: str | None = None  # cntn_cf_strain
    sex: str | None = None  # cntn_cf_sex

# all possible downstream results than need to be centralised and linked
class Assay(BaseModel):
    slims_id: str
    slims_link: str
    slims_pk: int
    mammoid: str | None = None  # cntn_cf_mammoid
    experiment: str
    exp_run: str
    exp_runsteps : list[str] = []
    assay_type: str | None = None  # cntn_fk_contentType displayValue
    original_content: str | None = None  # cntn_fk_originalContent displayValue (derivation link)
    external_link: str | None = None  # Omero, cBioPortal
    results: list[str] = []
