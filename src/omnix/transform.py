"""Reshape raw SLIMS ``Content`` records into the Tumor/Mouse/Assay models.

Column names are pinned in ``docs/xenograft-data-model.md``. Everything reads
from ``record.json_entity["columns"]`` (safe for absent/sparse columns) rather
than the attribute accessors, which raise on missing columns.
"""

from __future__ import annotations

from typing import Any

from .models import Assay, Mouse, Tumor

# --- low-level column access -------------------------------------------------


def _columns(record: Any) -> dict[str, dict]:
    return {c.get("name"): c for c in record.json_entity["columns"]}


def _val(cols: dict[str, dict], name: str) -> Any:
    col = cols.get(name)
    return col.get("value") if col else None


def _disp(cols: dict[str, dict], name: str) -> Any:
    col = cols.get(name)
    if not col:
        return None
    return col.get("displayValue")


def raw_dump(record: Any) -> dict[str, Any]:
    """All non-empty columns of a record as {name: value} -- stored as raw_json
    so a detail page can show every SLIMS field, not just the modeled ones."""
    out: dict[str, Any] = {}
    for c in record.json_entity["columns"]:
        name, value = c.get("name"), c.get("value")
        if name and value not in (None, "", []):
            out[name] = c.get("displayValue") or value
    return out


def _text(cols: dict[str, dict], name: str) -> str | None:
    """A column's value as a trimmed string (numbers rendered without .0)."""
    v = _val(cols, name)
    if v in (None, "", []):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


# --- record -> model ---------------------------------------------------------


def to_tumor(record: Any) -> Tumor:
    c = _columns(record)
    return Tumor(
        slims_id=_text(c, "cntn_id") or str(record.pk()),
        mammoid=_text(c, "cntn_cf_mammoid"),
        name=_text(c, "cntn_cf_Name"),
        tumor_type=_text(c, "cntn_cf_Type"),
        subtype=_text(c, "cntn_cf_subtype"),
        grade=_text(c, "cntn_cf_Grade"),
        er=_text(c, "cntn_cf_erShortText"),
        pr=_text(c, "cntn_cf_prShortText"),
        her2=_text(c, "cntn_cf_Her2"),
        ki67=_text(c, "cntn_cf_ki67ShortText"),
    )


def to_mouse(record: Any, treatment_lookup: dict[int, str] | None = None) -> Mouse:
    c = _columns(record)
    return Mouse(
        slims_id=_text(c, "cntn_id") or str(record.pk()),
        mammoid=_text(c, "cntn_cf_mammoid"),
        mouse_exp_nb=_text(c, "cntn_cf_mouseExpNb"),
        generation=_text(c, "cntn_cf_generation"),
        generation_mm=_text(c, "cntn_cf_generationMm"),
        treatment=_resolve_treatment(c, treatment_lookup or {}),
        mutations_raw=_text(c, "cntn_cf_mutations"),
        strain=_text(c, "cntn_cf_strain"),
        sex=_text(c, "cntn_cf_sex"),
        project=_text(c, "cntn_cf_project"),
    )


def to_assay(record: Any) -> Assay:
    c = _columns(record)
    return Assay(
        slims_id=_text(c, "cntn_id") or str(record.pk()),
        assay_type=_disp(c, "cntn_fk_contentType") or _text(c, "cntn_fk_contentType"),
        mammoid=_text(c, "cntn_cf_mammoid"),
        mouse_exp_nb=_text(c, "cntn_cf_mouseExpNb"),
        organ=_text(c, "cntn_cf_organ"),
        original_content=_disp(c, "cntn_fk_originalContent"),
    )


def _resolve_treatment(cols: dict[str, dict], lookup: dict[int, str]) -> str | None:
    """Treatment is an FK (list of Treatment content pks). Prefer the resolved
    displayValue; otherwise map pks through the Treatment lookup."""
    disp = _disp(cols, "cntn_cf_fk_treatment")
    if disp:
        return str(disp)
    raw = _val(cols, "cntn_cf_fk_treatment")
    if not raw:
        return None
    pks = raw if isinstance(raw, list) else [raw]
    labels = [lookup.get(pk) for pk in pks]
    labels = [x for x in labels if x]
    return ", ".join(labels) or None


def build_treatment_lookup(treatment_records: list[Any]) -> dict[int, str]:
    """pk -> best label for Treatment content, used to resolve mouse treatments."""
    lookup: dict[int, str] = {}
    for r in treatment_records:
        c = _columns(r)
        label = (
            _text(c, "cntn_cf_Name") or _text(c, "cntn_id") or _text(c, "cntn_barCode")
        )
        if label:
            lookup[r.pk()] = label
    return lookup


# --- linking + derived fields ------------------------------------------------


def normalize_mammoid(value: str | None) -> str | None:
    """Normalize the join key for equality matching. Conservative: trim + upper.
    Mouse mammoids are free text, so many will simply not match a tumor -- that
    is expected and surfaced as 'unmatched' in the UI, not silently dropped."""
    if not value:
        return None
    return value.strip().upper() or None


def _index_by_mammoid(items: list[Any]) -> dict[str, list[Any]]:
    index: dict[str, list[Any]] = {}
    for it in items:
        key = normalize_mammoid(it.mammoid)
        if key:
            index.setdefault(key, []).append(it)
    return index


def derive_tumor_fields(
    tumors: list[Tumor], mice: list[Mouse], assays: list[Assay]
) -> None:
    """Populate rna_sequenced / dna_sequenced / n_experiments / treatments on
    each tumor in place, by matching linked mice & assays on the mammoid key."""
    mice_by = _index_by_mammoid(mice)
    assays_by = _index_by_mammoid(assays)
    for t in tumors:
        key = normalize_mammoid(t.mammoid)
        linked_assays = assays_by.get(key, []) if key else []
        linked_mice = mice_by.get(key, []) if key else []

        assay_types = {a.assay_type for a in linked_assays}
        t.rna_sequenced = "Tissue for RNA" in assay_types
        t.dna_sequenced = "DNA" in assay_types  # 0 records today -> always False

        exp_nbs = {a.mouse_exp_nb for a in linked_assays if a.mouse_exp_nb}
        exp_nbs |= {m.mouse_exp_nb for m in linked_mice if m.mouse_exp_nb}
        t.n_experiments = len(exp_nbs)

        t.treatments = sorted({m.treatment for m in linked_mice if m.treatment})
