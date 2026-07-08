"""Flask app factory + routes. Serves read-only from the SQLite snapshot.

No SLIMS access here -- everything reads the file written by ``omnix snapshot``.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, Response, abort, g, render_template, request

from .. import store
from . import charts

# URL slug -> entity table + display config.
ENTITIES = {
    "tumors": {
        "entity": "tumor",
        "title": "Tumors",
        "columns": [
            ("slims_id", "ID"), ("mammoid", "Sample"), ("tumor_type", "Type"),
            ("subtype", "Subtype"), ("grade", "Grade"), ("her2", "HER2"),
            ("rna_sequenced", "RNA"), ("n_experiments", "#Exp"),
        ],
    },
    "mice": {
        "entity": "mouse",
        "title": "Mice",
        "columns": [
            ("slims_id", "ID"), ("mammoid", "Sample"), ("mouse_exp_nb", "Exp#"),
            ("generation", "Gen"), ("strain", "Strain"), ("sex", "Sex"),
            ("treatment", "Treatment"),
        ],
    },
    "assays": {
        "entity": "assay",
        "title": "Assays",
        "columns": [
            ("slims_id", "ID"), ("assay_type", "Type"), ("mammoid", "Sample"),
            ("mouse_exp_nb", "Exp#"), ("organ", "Organ"),
        ],
    },
}
ENTITY_TO_SLUG = {cfg["entity"]: slug for slug, cfg in ENTITIES.items()}
PER_PAGE = 50


def create_app(db_path: str | Path = store.DEFAULT_DB) -> Flask:  # noqa: PLR0915 (route registrations)
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path)

    def get_conn() -> sqlite3.Connection:
        if "conn" not in g:
            g.conn = store.connect(app.config["DB_PATH"], read_only=True)
        return g.conn

    @app.teardown_appcontext
    def _close(_exc) -> None:
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.context_processor
    def _inject():
        def qs(**overrides) -> str:
            """Current query string with overrides applied (drops empties)."""
            merged = {**request.args.to_dict(), **overrides}
            return urlencode({k: v for k, v in merged.items() if v not in (None, "")})

        def fmt_cell(col: str, value) -> str:
            if col in ("rna_sequenced", "dna_sequenced"):
                return "yes" if str(value) == "1" else "-"
            return "" if value is None else str(value)

        return {"entities": ENTITIES, "entity_to_slug": ENTITY_TO_SLUG, "qs": qs, "fmt_cell": fmt_cell}

    # --- dashboard ---------------------------------------------------------
    @app.route("/")
    def dashboard():
        conn = get_conn()
        return render_template(
            "dashboard.html", meta=store.get_meta(conn), stats=charts.summary(conn)
        )

    # --- entity list + htmx rows partial -----------------------------------
    @app.route("/<slug>")
    def entity_list(slug: str):
        cfg = ENTITIES.get(slug) or abort(404)
        conn = get_conn()
        entity = cfg["entity"]
        widgets = [
            {"col": col, "options": store.distinct_values(conn, entity, col),
             "value": request.args.get(col, "")}
            for col in store.FILTER_COLUMNS[entity]
        ]
        rows, total, page = _page(conn, entity)
        return render_template(
            "list.html", cfg=cfg, slug=slug, widgets=widgets,
            rows=rows, total=total, page=page, per_page=PER_PAGE, args=request.args,
        )

    @app.route("/<slug>/rows")
    def entity_rows(slug: str):
        cfg = ENTITIES.get(slug) or abort(404)
        conn = get_conn()
        rows, total, page = _page(conn, cfg["entity"])
        return render_template(
            "_rows.html", cfg=cfg, slug=slug, rows=rows, total=total,
            page=page, per_page=PER_PAGE, args=request.args,
        )

    # --- detail + drill-down ----------------------------------------------
    @app.route("/tumor/<slims_id>")
    def tumor_detail(slims_id: str):
        conn = get_conn()
        row = store.get_one(conn, "tumor", slims_id) or abort(404)
        linked = store.linked_to_tumor(conn, row["mammoid"])
        return render_template("detail_tumor.html", row=row, linked=linked, raw=_raw(row))

    @app.route("/mouse/<slims_id>")
    def mouse_detail(slims_id: str):
        row = store.get_one(get_conn(), "mouse", slims_id) or abort(404)
        return render_template("detail_generic.html", entity="mouse", title="Mouse", row=row, raw=_raw(row))

    @app.route("/assay/<slims_id>")
    def assay_detail(slims_id: str):
        row = store.get_one(get_conn(), "assay", slims_id) or abort(404)
        return render_template("detail_generic.html", entity="assay", title="Assay", row=row, raw=_raw(row))

    # --- search ------------------------------------------------------------
    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        hits = store.search(get_conn(), q) if q else []
        template = "_search_results.html" if request.headers.get("HX-Request") else "search.html"
        return render_template(template, q=q, hits=hits)

    # --- export ------------------------------------------------------------
    @app.route("/export/<slug>.<fmt>")
    def export(slug: str, fmt: str):
        cfg = ENTITIES.get(slug) or abort(404)
        if fmt not in ("csv", "json"):
            abort(404)
        conn = get_conn()
        rows, _ = store.list_entity(conn, cfg["entity"], dict(request.args), limit=1_000_000, offset=0)
        dicts = [{k: r[k] for k in r.keys() if k != "raw_json"} for r in rows]
        if fmt == "json":
            return Response(json.dumps(dicts, indent=2), mimetype="application/json",
                            headers={"Content-Disposition": f"attachment; filename={slug}.json"})
        buf = io.StringIO()
        if dicts:
            writer = csv.DictWriter(buf, fieldnames=list(dicts[0].keys()))
            writer.writeheader()
            writer.writerows(dicts)
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={slug}.csv"})

    # --- heatmap (implemented in the heatmap milestone) --------------------
    @app.route("/heatmap")
    def heatmap():
        conn = get_conn()
        matrix = store.mutation_matrix(conn, "mouse")
        svg = charts.oncoprint_svg(matrix)
        template = "_heatmap.html" if request.headers.get("HX-Request") else "heatmap.html"
        return render_template(template, svg=svg, matrix=matrix)

    return app


# --- helpers -----------------------------------------------------------------


def _page(conn: sqlite3.Connection, entity: str):
    """Read page + filters from the request and return (rows, total, page)."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    rows, total = store.list_entity(
        conn, entity, dict(request.args), limit=PER_PAGE, offset=(page - 1) * PER_PAGE
    )
    return rows, total, page


def _raw(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["raw_json"] or "{}")
    except (KeyError, json.JSONDecodeError):
        return {}
