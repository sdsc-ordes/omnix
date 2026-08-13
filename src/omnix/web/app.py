"""Flask app factory + routes. Serves read-only from the SQLite snapshot.

No SLIMS access here -- everything reads the file written by ``omnix snapshot``.
The three list pages (tumors / mice / assays) are the typed views over the
``content`` table; the detail page works for any content pk and shows its
projected fields, its provenance chain, and sibling content sharing its sample.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, Response, abort, g, render_template, request

from .. import content_types, store
from ..slims_spec import SLIMS_BASE_URL
from . import charts

PER_PAGE = 50


def create_app(db_path: str | Path = store.DEFAULT_DB) -> Flask:
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

        def fmt_cell(kind, col: str, value) -> str:
            if kind is not None and col in kind.bool_columns():
                return "yes" if str(value) == "1" else "—"
            return "" if value is None else str(value)

        return {"kinds": content_types.KINDS, "qs": qs, "fmt_cell": fmt_cell}

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
        kind = content_types.BY_SLUG.get(slug) or abort(404)
        conn = get_conn()
        widgets = [
            {
                "col": col,
                "options": store.distinct_values(conn, kind.view, col),
                "value": request.args.get(col, ""),
            }
            for col in kind.filter_columns()
        ]
        rows, total, page, sort_by, sort_order = _page(conn, kind.view)
        return render_template(
            "list.html",
            kind=kind,
            widgets=widgets,
            rows=rows,
            total=total,
            page=page,
            per_page=PER_PAGE,
            sort_by=sort_by,
            sort_order=sort_order
        )

    @app.route("/<slug>/rows")
    def entity_rows(slug: str):
        kind = content_types.BY_SLUG.get(slug) or abort(404)
        conn = get_conn()
        rows, total, page, sort_by, sort_order = _page(conn, kind.view)
        return render_template(
            "_rows.html",
            kind=kind,
            rows=rows,
            total=total,
            page=page,
            per_page=PER_PAGE,
            sort_by=sort_by,
            sort_order=sort_order
        )

    # --- content detail (any type) + drill-downs ---------------------------
    @app.route("/content/<int:pk>")
    def content_detail(pk: int):
        conn = get_conn()
        base = store.get_content(conn, pk) or abort(404)
        kind = content_types.kind_for_content_type(base["content_type"])
        row = store.get_one_in_view(conn, kind.view, pk) or base
        return render_template(
            "detail.html",
            kind=kind,
            row=row,
            provenance=store.provenance_for_content(conn, pk),
            linked=store.linked_content_by_kind(conn, row["pk"]) if kind.slug == "tumors" else [],
            raw=_raw(base),
            slims_base_url=SLIMS_BASE_URL,
        )

    # --- export ------------------------------------------------------------
    @app.route("/export/<slug>.<fmt>")
    def export(slug: str, fmt: str):
        kind = content_types.BY_SLUG.get(slug) or abort(404)
        if fmt not in ("csv", "json"):
            abort(404)
        conn = get_conn()
        rows, _ = store.list_entity(conn, kind.view, dict(request.args), limit=1_000_000, offset=0)
        drop = {"raw_json"}
        dicts = [{k: r[k] for k in r.keys() if k not in drop} for r in rows]
        if fmt == "json":
            return Response(
                json.dumps(dicts, indent=2), mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={slug}.json"},
            )
        buf = io.StringIO()
        if dicts:
            writer = csv.DictWriter(buf, fieldnames=list(dicts[0].keys()))
            writer.writeheader()
            writer.writerows(dicts)
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={slug}.csv"},
        )

    return app


# --- helpers -----------------------------------------------------------------


def _page(conn: sqlite3.Connection, view: str):
    """Read page + filters from the request, return (rows, total, page)."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    default_sort_by = "n_xenografts" if view == "tumors" else "exp_name"
    default_order = "desc" if view == "tumors" else "asc"

    sort_by = request.args.get("sort", default_sort_by)
    sort_order = request.args.get("dir", default_order)

    rows, total = store.list_entity(
        conn,
        view,
        dict(request.args),
        sort_by=sort_by,
        sort_order=sort_order,
        limit=PER_PAGE,
        offset=(page - 1) * PER_PAGE
    )
    return rows, total, page, sort_by, sort_order


def _raw(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["raw_json"] or "{}")
    except (KeyError, IndexError, json.JSONDecodeError):
        return {}
