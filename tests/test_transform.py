"""Tests for the raw-record -> model reshape and derived fields."""

from omnix import transform
from omnix.models import Assay, Mouse, Tumor


def test_to_tumor_maps_columns(tumor_record):
    t = transform.to_tumor(tumor_record)
    assert t.slims_id == "TUMOR_00000900"
    assert t.mammoid == "T-900"
    assert t.tumor_type == "BRCA1"
    assert t.her2 == "Negative"
    assert t.er == "90"


def test_to_mouse_resolves_treatment_fk(mouse_record, treatment_record):
    lookup = transform.build_treatment_lookup([treatment_record])
    m = transform.to_mouse(mouse_record, lookup)
    assert m.slims_id == "00009001"
    assert m.mouse_exp_nb == "5"  # numeric coerced to string
    assert m.generation == "G7(5)"
    assert m.treatment == "tamoxifen (chow)"  # resolved from pk 123


def test_to_assay_type_from_display(blood_record, tissue_record):
    assert transform.to_assay(blood_record).assay_type == "Blood Sample"
    tissue = transform.to_assay(tissue_record)
    assert tissue.assay_type == "Tissue for RNA"
    assert tissue.organ == "3L"
    assert tissue.original_content is None


def test_derive_tumor_fields_links_on_mammoid():
    tumors = [Tumor(slims_id="T1", mammoid="T-900")]
    mice = [Mouse(slims_id="M1", mammoid="T-900", mouse_exp_nb="5", treatment="tam")]
    assays = [
        Assay(slims_id="A1", assay_type="Tissue for RNA", mammoid="T-900", mouse_exp_nb="5"),
        Assay(slims_id="A2", assay_type="Blood Sample", mammoid="T-900"),
    ]
    transform.derive_tumor_fields(tumors, mice, assays)
    t = tumors[0]
    assert t.rna_sequenced is True
    assert t.dna_sequenced is False
    assert t.n_experiments == 1
    assert t.treatments == ["tam"]


def test_derive_tumor_fields_no_match_is_empty():
    tumors = [Tumor(slims_id="T1", mammoid="T-900")]
    transform.derive_tumor_fields(tumors, mice=[], assays=[])
    assert tumors[0].rna_sequenced is False
    assert tumors[0].n_experiments == 0
    assert tumors[0].treatments == []


