"""Route tests via the Flask test client over a seeded temp snapshot."""

import json


def test_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Xenograft snapshot" in r.data


def test_list_and_filter(client):
    assert b"TUMOR_00000900" in client.get("/tumors").data

    hit = client.get("/tumors/rows?tumor_type=BRCA1")
    assert b"TUMOR_00000900" in hit.data

    miss = client.get("/tumors/rows?tumor_type=NOPE")
    assert b"No matching records" in miss.data


def test_unknown_slug_404(client):
    assert client.get("/widgets").status_code == 404


def test_tumor_drilldown(client):
    r = client.get("/tumor/TUMOR_00000900")
    assert r.status_code == 200
    assert b"00009001" in r.data  # linked mouse
    assert b"BRI_CV_00000900" in r.data  # linked tissue assay


def test_mouse_detail(client):
    assert client.get("/mouse/00009001").status_code == 200




def test_export_csv(client):
    r = client.get("/export/tumors.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert r.data.splitlines()[0].startswith(b"slims_id")


def test_export_json_respects_filter(client):
    r = client.get("/export/tumors.json?tumor_type=BRCA1")
    data = json.loads(r.data)
    assert len(data) == 1
    assert data[0]["slims_id"] == "TUMOR_00000900"
    assert "raw_json" not in data[0]
