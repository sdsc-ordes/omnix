"""What each content type looks like on the website.

Each entry becomes a nav item, a list page, and a SQL view over the ``content`` table
(built by ``store.build_type_views``). The engine below the block compiles those
entries into SQL.

A content row's type-specific columns live in ``raw_json``; a field just names
the SLIMS column to pull out. Promoted columns and provenance-derived values use
a short prefix so you never have to say *how* a value is fetched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ============================================================================
#  SQL entries to view on UI
#  One entry per page. Fields are 3- or 4-tuples:
#
#      (key, "Header", source [, flags])
#
#  key      short column name used in the view / URL (letters, digits, _)
#  Header   what the column is called in the UI
#  source   where the value comes from:
#             "cntn_cf_Grade"   any SLIMS column  -> read from raw_json
#             "mammoid"         a promoted column already on `content`
#                               (slims_id, content_type, mammoid, original_content)
#             "@n_xenografts"  a derived value  (see DERIVED further down)
#  flags    optional string, any of:
#             l  show this column in the list table
#             f  offer it as a filter widget
#             b  render as yes / -- (boolean)
#
#  To give an assay type its own page instead of sharing the Assays page,
#  copy the assays entry and give it a single-item `types` list.
# ============================================================================

SPEC: list[dict] = [
    {
        "slug": "tumors",
        "title": "Tumors",
        "types": ["Tumor", "Mets"],
        "fields": [
            ("slims_id",      "ID",      "slims_id",              "l"),
            ("mammoid",       "Mammoid", "mammoid",              "lf"),
            ("exp_name",          "Exp. Name","@exp_name",        "lf"),
            ("tumor_type",    "Type",    "cntn_cf_Type",          "lf"),
            ("subtype",       "Subtype", "cntn_cf_subtype",       "lf"),
            ("grade",         "Grade",   "cntn_cf_Grade",         "lf"),
            ("er",            "ER",      "cntn_cf_erShortText",   ""),
            ("pr",            "PR",      "cntn_cf_prShortText",   ""),
            ("her2",          "HER2",    "cntn_cf_Her2",          ""),
            ("ki67",          "Ki67",    "cntn_cf_ki67ShortText", ""),
            ("rna_sequenced", "RNA",     "@rna_sequenced",        "lfb"),
            ("n_xenografts",  "#PDX",    "@n_xenografts",         "l"),
        ],
    },
    {
        "slug": "mice",
        "title": "Mice",
        "types": ["Mouse"],
        "fields": [
            ("slims_id",      "ID",         "slims_id",             "l"),
            ("mammoid",       "Mammoid",    "mammoid",              "lf"),
            ("exp_name",      "Exp. Name",  "@exp_name",            "lf"),
            ("mouse_exp_nb",  "Mouse Exp #","cntn_cf_mouseExpNb",   "l"),
            ("strain",        "Strain",     "cntn_cf_strain",       "lf"),
            ("sex",           "Sex",        "cntn_cf_sex",          "lf"),
            ("treatment",     "Treatment",  "cntn_cf_fk_treatment", "lf"),
        ],
    },
    {
        "slug": "assays",
        "title": "Assays",
        "types": ["Slide", "Blood Sample", "Tissue for RNA", "Blood for analysis"],   # to be extended
        "fields": [
            ("slims_id",         "ID",            "slims_id",           "l"),
            ("assay_type",       "Type",          "content_type",       "lf"),
            ("mammoid",          "Mammoid",       "mammoid",            "lf"),
            ("exp_name",         "Exp. Name",     "@exp_name",          "lf"),
            ("original_content", "Derived from",  "original_content",   "l"),
        ],
    },
]

# ============================================================================
#  Derived values usable via "@name" above. Each is a scalar SQL expression
#  over the content row aliased `c`, reading the provenance graph (or other
#  content) rather than a SLIMS column. Add one here to expose it as a field.
# ============================================================================

DERIVED: dict[str, str] = {
    "exp_name": (
            "(SELECT GROUP_CONCAT(DISTINCT e.name) "
            "FROM runstep_content l "
            "JOIN experiment e ON e.pk = l.experiment_pk "
            "WHERE l.content_pk = c.pk)"
        ),
    "n_xenografts": (
        "(SELECT COUNT(DISTINCT m.pk) "
        "FROM runstep_content l2 "
        "JOIN content m ON m.pk = l2.content_pk "
        "WHERE m.content_type = 'Mouse' "
        "AND l2.experiment_pk IN ("
        "SELECT l.experiment_pk FROM runstep_content l WHERE l.content_pk = c.pk))"
    ),
    # Heuristic kept from the old mammoid-match logic: a "Tissue for RNA"
    # content shares this row's sample id.
    "rna_sequenced": (
        "(SELECT EXISTS(SELECT 1 FROM content r "
        "WHERE r.mammoid IS NOT NULL AND r.mammoid = c.mammoid "
        "AND r.content_type = 'Tissue for RNA'))"
    ),
}

# ============================================================================
#  Engine to display
# ============================================================================

# Base columns every view exposes, mapped to their real column on `content`.
BASE_COLUMNS: dict[str, str] = {
    "pk": "pk",
    "slims_id": "slims_id",
    "slims_link": "slims_link",
    "type": "content_type",
    "mammoid": "mammoid",
    "raw_json": "raw_json",
}

# Promoted columns a field may reference directly (everything else is raw_json).
PROMOTED = {"slims_id", "content_type", "mammoid", "original_content", "slims_link"}

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check(name: str) -> None:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe identifier {name!r}")


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    json_col: str | None = None
    content_col: str | None = None
    derived: str | None = None
    in_list: bool = False
    filterable: bool = False
    is_bool: bool = False

    def sql_expr(self) -> str:
        """SELECT expression producing this field, aliased to ``key``."""
        if self.json_col is not None:
            _check(self.json_col)
            expr = f"json_extract(c.raw_json, '$.{self.json_col}')"
        elif self.content_col is not None:
            _check(self.content_col)
            expr = f"c.{self.content_col}"
        elif self.derived is not None:
            if self.derived not in DERIVED:
                raise KeyError(f"unknown derived field {self.derived!r}")
            expr = DERIVED[self.derived]
        else:
            raise ValueError(f"field {self.key!r} has no source")
        _check(self.key)
        return f"{expr} AS {self.key}"


@dataclass(frozen=True)
class Kind:
    slug: str
    view: str
    title: str
    fields: tuple[Field, ...]
    include_types: tuple[str, ...] = ()
    exclude_types: tuple[str, ...] = ()
    hidden: bool = False  # built as a view but kept out of the nav

    def where_clause(self) -> str:
        if self.include_types:
            return "c.content_type IN (" + ",".join(_lit(t) for t in self.include_types) + ")"
        if self.exclude_types:
            return "c.content_type NOT IN (" + ",".join(_lit(t) for t in self.exclude_types) + ")"
        return "1=1"

    def list_columns(self) -> list[tuple[str, str]]:
        return [(f.key, f.label) for f in self.fields if f.in_list]

    def filter_columns(self) -> list[str]:
        return [f.key for f in self.fields if f.filterable]

    def bool_columns(self) -> set[str]:
        return {f.key for f in self.fields if f.is_bool}


def _compile_field(spec: tuple) -> Field:
    key, label, source = spec[0], spec[1], spec[2]
    flags = spec[3] if len(spec) > 3 else ""
    kwargs: dict = {}
    if source.startswith("@"):
        kwargs["derived"] = source[1:]
    elif source in PROMOTED:
        kwargs["content_col"] = source
    else:
        kwargs["json_col"] = source
    return Field(
        key=key,
        label=label,
        in_list="l" in flags,
        filterable="f" in flags,
        is_bool="b" in flags,
        **kwargs,
    )


def _compile(entry: dict) -> Kind:
    slug = entry["slug"]
    return Kind(
        slug=slug,
        view=entry.get("view", slug),  # view name defaults to the slug
        title=entry["title"],
        fields=tuple(_compile_field(f) for f in entry["fields"]),
        include_types=tuple(entry.get("types", ())),
        exclude_types=tuple(entry.get("exclude_types", ())),
    )


#: Visible kinds -- nav, dashboard, list pages.
KINDS: tuple[Kind, ...] = tuple(_compile(e) for e in SPEC)

#: Fallback for content whose type is in none of the pages above (reachable via
#: provenance / same-sample links). Built as a hidden view so its detail page
#: still renders; also serves as an "all content" list at /all_content.
_FALLBACK = Kind(
    slug="all_content",
    view="all_content",
    title="Content",
    hidden=True,
    fields=(
        Field("slims_id", "ID", content_col="slims_id", in_list=True),
        Field("assay_type", "Type", content_col="content_type", in_list=True, filterable=True),
        Field("mammoid", "Sample", content_col="mammoid", in_list=True, filterable=True),
    ),
)

#: Everything that gets a SQL view (visible + fallback).
ALL_KINDS: tuple[Kind, ...] = (*KINDS, _FALLBACK)

BY_SLUG: dict[str, Kind] = {k.slug: k for k in ALL_KINDS}
BY_VIEW: dict[str, Kind] = {k.view: k for k in ALL_KINDS}


def kind_for_content_type(content_type: str | None) -> Kind:
    """Which kind a stored content row is shown as (drives the detail page)."""
    if content_type:
        for k in KINDS:
            if content_type in k.include_types:
                return k
            if k.exclude_types and content_type not in k.exclude_types:
                return k
    return _FALLBACK
