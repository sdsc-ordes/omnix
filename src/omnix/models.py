"""Reference shapes for the xenograft data model -- not used at runtime.

This was made before the move to a generic ``content`` table projected into typed SQL
views (see ``content_types`` and ``store.build_type_views``). Nothing imports
them: the ETL writes row dicts straight from ``transform``, and the web layer
reads the views. ``ContentLinkChain`` is the exception worth reading -- it
documents the provenance edge now persisted as the ``runstep_content`` table.

Kept as a sketch of the intended domain structure and of which SLIMS fields
map onto what. Expect drift: field names and derived values here are not
guaranteed to match the current views, and the ``docs/xenograft-data-model.md``
coverage table they were written against may also be out of date.
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
