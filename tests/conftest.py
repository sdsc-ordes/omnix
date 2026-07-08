"""Shared test fixtures.

We build synthetic SLIMS records (no real lab/patient data committed) that mimic
the ``record.json_entity`` shape the transform layer reads.
"""

from __future__ import annotations

import pytest

from omnix import store, transform
from omnix.web.app import create_app


class FakeRecord:
    """Minimal stand-in for slims.internal.Record."""

    def __init__(self, columns: list[dict], pk: int):
        self.json_entity = {"columns": columns, "pk": pk, "tableName": "Content"}
        self._pk = pk

    def pk(self) -> int:
        return self._pk

    def table_name(self) -> str:
        return "Content"


def col(name: str, value, display=None, title=None) -> dict:
    return {"name": name, "value": value, "displayValue": display, "title": title or name}


@pytest.fixture
def tumor_record() -> FakeRecord:
    return FakeRecord(
        [
            col("cntn_id", "TUMOR_00000900"),
            col("cntn_cf_mammoid", "T-900"),
            col("cntn_cf_Name", "demo-tumor"),
            col("cntn_cf_Type", "BRCA1"),
            col("cntn_cf_subtype", "Lum A-B"),
            col("cntn_cf_Grade", "2"),
            col("cntn_cf_erShortText", "90"),
            col("cntn_cf_Her2", "Negative"),
            col("cntn_cf_ageMammo", 33),  # patient field -- ignored by the model
        ],
        pk=10900,
    )


@pytest.fixture
def mouse_record() -> FakeRecord:
    return FakeRecord(
        [
            col("cntn_id", "00009001"),
            col("cntn_cf_mammoid", "T-900"),
            col("cntn_cf_mouseExpNb", 5),
            col("cntn_cf_generation", "G7(5)"),
            col("cntn_cf_generationMm", "P1"),
            col("cntn_cf_fk_treatment", [123]),
            col("cntn_cf_mutations", "AF1 WT"),
            col("cntn_cf_strain", "ER alfa AF2"),
            col("cntn_cf_sex", "f"),
            col("cntn_cf_project", "cagnet"),
        ],
        pk=19001,
    )


@pytest.fixture
def treatment_record() -> FakeRecord:
    return FakeRecord([col("cntn_cf_Name", "tamoxifen (chow)")], pk=123)


@pytest.fixture
def blood_record() -> FakeRecord:
    return FakeRecord(
        [
            col("cntn_id", "BLOOD_00000900"),
            col("cntn_fk_contentType", 21, display="Blood Sample"),
            col("cntn_cf_mammoid", "T-900"),
            col("cntn_fk_originalContent", 766, display="MAMMO_00000038"),
        ],
        pk=21900,
    )


@pytest.fixture
def tissue_record() -> FakeRecord:
    return FakeRecord(
        [
            col("cntn_id", "BRI_CV_00000900"),
            col("cntn_fk_contentType", 5, display="Tissue for RNA"),
            col("cntn_cf_mammoid", "T-900"),
            col("cntn_cf_mouseExpNb", 5),
            col("cntn_cf_organ", "3L"),
        ],
        pk=5900,
    )


@pytest.fixture
def seeded_db(tmp_path, tumor_record, mouse_record, treatment_record, blood_record, tissue_record):
    """A temp SQLite snapshot built from the synthetic records."""
    lookup = transform.build_treatment_lookup([treatment_record])
    tumors = [transform.to_tumor(tumor_record)]
    mice = [transform.to_mouse(mouse_record, lookup)]
    assays = [transform.to_assay(blood_record), transform.to_assay(tissue_record)]
    transform.derive_tumor_fields(tumors, mice, assays)
    mutations = [mut for m in mice for mut in transform.parse_mouse_mutations(m)]

    db_path = tmp_path / "snap.db"
    conn = store.connect(db_path, read_only=False)
    store.write_snapshot(conn, tumors, mice, assays, mutations, "http://test", {})
    conn.close()
    return db_path


@pytest.fixture
def client(seeded_db):
    app = create_app(seeded_db)
    app.config.update(TESTING=True)
    return app.test_client()
