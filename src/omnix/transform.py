"""Reshape raw SLIMS records into the row dicts that ``store`` writes as SQL tables.

Everything reads from ``record.json_entity["columns"]``. Each row dict's keys
are exactly the SQL column names for its table.

There is one generic ``content`` row for each SLIMS content record.
The Tumor/Mouse/Assay types are projected out of the stored ``content``
table by SQL views (see ``content_types`` and ``store.build_type_views``).
"""


from __future__ import annotations

import json
from typing import Any

from . import slims_spec, content_types



# --- low-level column access -------------------------------------------------


def _columns(
    record: Any,
) -> dict[str, dict]:
    return {c.get("name"): c for c in record.json_entity.get("columns", []) if c.get("name")}


def _val(
    cols: dict[str, dict],
    name: str | None,
) -> Any:
    if name is None:
        return None
    col = cols.get(name)
    return col.get("value") if col else None


def _best_display(col: dict) -> Any:
    """Best human label for ONE column dict: joined multi-fk, multi-fk, single fk."""
    joined = col.get("joinedDisplayValue")
    if joined not in (None, ""):
        return joined
    values = col.get("displayValues")
    if values:
        return ", ".join(str(v) for v in values if v not in (None, ""))
    disp = col.get("displayValue")
    if disp not in (None, ""):
        return disp
    return None


def _disp(cols: dict[str, dict], name: str | None) -> Any:
    """Best human label for a named column in a record's column map."""
    if name is None:
        return None
    col = cols.get(name)
    return _best_display(col) if col else None


def _link(v: Any) -> str | None:
    """Extract url from a html link field, e.g. `<a href="url">link text</a>` -> `url`."""
    parts = v.split('href="')
    if len(parts) > 1:
        return parts[1].split('"')[0].strip()
    else:
        return None


def _text(
    cols: dict[str, dict],
    name: str | None,
) -> str | None:
    """A column's value as a trimmed string (numbers rendered without .0)."""
    v = _val(cols, name)
    if v in (None, "", []):
        return None
    if name == slims_spec.EXPERIMENT.omerolink:
        return _link(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def raw_dump(
    record: Any,
) -> dict[str, Any]:
    """All non-empty columns of a record as {name: (title, value)} -- stored as raw_json
    so a detail page can show every SLIMS field, not just the modeled ones."""
    out: dict[str, Any] = {}
    for c in record.json_entity["columns"]:
        name, title, value = c.get("name"), c.get("title"), c.get("value")
        if not name or not title or value in (None, "", []):
            continue
        display = _best_display(c)
        out[name] = (title, display if display is not None else value)
    return out


def label(cols: dict[str, dict], name: str | None) -> str | None:
    """Resolved label if the column is an fk, else the raw value as text."""
    disp = _disp(cols, name)
    if disp not in (None, ""):
        return str(disp).strip()
    return _text(cols, name)


# --- slims record -> sql row -----------------------------------------------------------

def experiment_row(
    record: Any,
    project_pk: int,
) -> dict[str, Any]:
    c = _columns(record)
    return {
        "pk": record.pk(),
        "project_pk": project_pk,
        "name": _text(c, slims_spec.EXPERIMENT.name),
        "omerolink": _text(c, _link(slims_spec.EXPERIMENT.omerolink)),
        "raw_json": json.dumps(raw_dump(record)),
    }


def run_row(
    record: Any,
    experiment_pk: int | None = None,
) -> dict[str, Any]:
    """`experiment_pk` is read off the record itself; pass it only as a fallback
    for instances where the fk is not returned in the column list."""
    c = _columns(record)
    parent = int(_val(c, slims_spec.EXPERIMENT_RUN.parent_fk)) or experiment_pk
    return {
        "pk": record.pk(),
        "experiment_pk": parent,
        "name": _text(c, slims_spec.EXPERIMENT_RUN.name),
        "raw_json": json.dumps(raw_dump(record)),
    }


def runstep_row(
    record: Any,
    experiment_by_run: dict[int, int] | None = None
) -> dict[str, Any]:
    c = _columns(record)
    run_pk = int(_val(c, slims_spec.EXPERIMENT_RUN_STEP.parent_fk))
    return {
        "pk": record.pk(),
        "exp_run_pk": run_pk,
        "experiment_pk": (experiment_by_run or {}).get(run_pk),
        "name": _text(c, slims_spec.EXPERIMENT_RUN_STEP.name),
        "raw_json": json.dumps(raw_dump(record)),
    }


def content_link_row(
    record: Any,
    run_by_step: dict[int, int],
    experiment_by_run: dict[int, int],
) -> dict[str, Any] | None:
    """One ExperimentRunStepContent row -> the provenance edge.

    Returns None when the link has no content pk (an empty step slot).
    """
    c = _columns(record)
    content_pk = int(_val(c, slims_spec.RUN_STEP_CONTENT_FK_CONTENT))
    if content_pk is None:
        return None
    runstep_pk = int(_val(c, slims_spec.RUN_STEP_CONTENT.parent_fk))
    run_pk = run_by_step.get(runstep_pk)
    return {
        "runstep_content_pk": record.pk(),
        "runstep_pk": runstep_pk,
        "exp_run_pk": run_pk,
        "experiment_pk": experiment_by_run.get(run_pk),
        "content_pk": content_pk,
    }


def content_row(
    record: Any,
) -> dict[str, Any]:
    """A Content record: promoted columns + the full raw dump."""
    c = _columns(record)
    row: dict[str, Any] = {"pk": record.pk()}
    for db_col, slims_col in content_types.PROMOTED_CONTENT_COLUMNS.items():
        row[db_col] = label(c, slims_col)
    row["raw_json"] = json.dumps(raw_dump(record))
    return row
