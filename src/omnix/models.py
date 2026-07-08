"""Typed domain models for the xenograft export.

These mirror the target shape in ``docs/xenograft-data-model.md``. Fields are
optional wherever the underlying SLIMS custom field is sparsely populated (see
the coverage table in that doc). The raw SLIMS column dump is kept separately by
the store, not on these models -- these stay clean for JSON export.
"""

from __future__ import annotations

from pydantic import BaseModel


class Mutation(BaseModel):
    """One parsed (gene, status) call for a sample -- feeds the oncoprint."""

    sample_kind: str  # "mouse" | "tumor"
    sample_id: str  # the owning sample's slims_id
    gene: str
    status: str  # e.g. "ko", "wt", "het", "positive", "unparsed"


class Tumor(BaseModel):
    slims_id: str
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
    dna_sequenced: bool = False
    n_experiments: int = 0
    treatments: list[str] = []


class Mouse(BaseModel):
    slims_id: str
    mammoid: str | None = None  # cntn_cf_mammoid (free text on mice -- unreliable join)
    mouse_exp_nb: str | None = None  # cntn_cf_mouseExpNb
    generation: str | None = None  # cntn_cf_generation ("G..." series)
    generation_mm: str | None = None  # cntn_cf_generationMm ("P..." series)
    treatment: str | None = None  # cntn_cf_fk_treatment (resolved label)
    mutations_raw: str | None = None  # cntn_cf_mutations (free text)
    strain: str | None = None  # cntn_cf_strain
    sex: str | None = None  # cntn_cf_sex
    project: str | None = None  # cntn_cf_project


class Assay(BaseModel):
    slims_id: str
    assay_type: str | None = None  # cntn_fk_contentType displayValue
    mammoid: str | None = None  # cntn_cf_mammoid
    mouse_exp_nb: str | None = None  # cntn_cf_mouseExpNb
    organ: str | None = None  # cntn_cf_organ
    original_content: str | None = None  # cntn_fk_originalContent displayValue (derivation link)
