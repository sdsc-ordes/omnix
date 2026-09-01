# tests/test_web.py

import pytest
import shutil
from pathlib import Path

from omnix import content_types, store

from omnix.web.app import create_app


@pytest.fixture
def test_db(tmp_path):
    source = Path("tests/data/test.db")
    tmp_db_path = tmp_path / "tmp.db"

    shutil.copy(source, tmp_db_path)

    # Rebuild type tables in case model changed
    conn = store.connect(tmp_db_path)
    store.build_type_tables(conn)
    conn.close()

    return tmp_db_path



@pytest.fixture
def app(test_db):
    app = create_app(test_db)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_templates_compile(app):
    for template in app.jinja_env.list_templates():
        app.jinja_env.get_template(template)


def test_dashboard_renders(client):
    response = client.get("/")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "kind",
    content_types.KINDS,
    ids=lambda kind: kind.slug,
)
def test_list_pages_render(client, kind):
    response = client.get(f"/{kind.slug}")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "kind",
    content_types.KINDS,
    ids=lambda kind: kind.slug,
)
def test_detail_pages_render(client, kind, test_db):
    conn = store.connect(test_db, read_only=True)

    try:
        rows, _ = store.list_entity(
            conn,
            kind.view,
            store.ListOptions(
                filters={},
                limit=1,
                offset=0)
        )
    finally:
        conn.close()

    if not rows:
        pytest.skip(f"No {kind.slug} available in snapshot")

    response = client.get(f"/content/{rows[0]['pk']}")

    assert response.status_code == 200
