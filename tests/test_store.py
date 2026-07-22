"""Tests for the SQLite store: write, filter, drill-down, pagination."""

from omnix import store


def test_meta_and_counts(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    meta = store.get_meta(conn)
    assert meta["counts"] == {"tumor": 1, "mouse": 1, "assay": 2}
    assert meta["source_url"] == "http://test"


def test_list_entity_and_filter(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    rows, total = store.list_entity(conn, "tumor")
    assert total == 1
    assert rows[0]["tumor_type"] == "BRCA1"

    rows, total = store.list_entity(conn, "tumor", {"tumor_type": "BRCA1"})
    assert total == 1
    rows, total = store.list_entity(conn, "tumor", {"tumor_type": "NOPE"})
    assert total == 0


def test_filter_ignores_unknown_column(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    # An unwhitelisted column must be ignored, not injected into SQL.
    _, total = store.list_entity(conn, "tumor", {"er": "90; DROP TABLE tumor"})
    assert total == 1  # filter skipped, table intact


def test_pagination(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    rows, total = store.list_entity(conn, "assay", limit=1, offset=0)
    assert total == 2
    assert len(rows) == 1


def test_get_one(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    assert store.get_one(conn, "tumor", "TUMOR_00000900")["mammoid"] == "T-900"
    assert store.get_one(conn, "tumor", "MISSING") is None


def test_linked_to_tumor_drilldown(seeded_db):
    conn = store.connect(seeded_db, read_only=True)
    linked = store.linked_to_tumor(conn, "T-900")
    assert {m["slims_id"] for m in linked["mice"]} == {"00009001"}
    assert {a["slims_id"] for a in linked["assays"]} == {"BLOOD_00000900", "BRI_CV_00000900"}


