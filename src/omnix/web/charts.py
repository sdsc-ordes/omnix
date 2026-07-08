"""Aggregation for the summary panel and (in the heatmap milestone) the SVG
oncoprint. Pure functions over a read-only SQLite connection."""

from __future__ import annotations

import sqlite3
from collections import Counter
from html import escape
from typing import Any

# Mutation status -> categorical class (colors live in app.css, theme-aware).
# Fixed order (never cycled): ko/het/wt/tg are identity slots; unparsed is neutral.
STATUS_ORDER = ["ko", "het", "wt", "tg", "unparsed"]


def _breakdown(conn: sqlite3.Connection, entity: str, col: str, top: int = 8) -> list[tuple[str, int]]:
    rows = conn.execute(
        f"SELECT {col} k, COUNT(*) n FROM {entity} "
        f"WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col} ORDER BY n DESC LIMIT ?",
        (top,),
    ).fetchall()
    return [(r["k"], r["n"]) for r in rows]


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counts + small breakdowns for the dashboard / stats panel."""
    tumor_total = conn.execute("SELECT COUNT(*) FROM tumor").fetchone()[0]
    rna = conn.execute("SELECT COUNT(*) FROM tumor WHERE rna_sequenced = 1").fetchone()[0]
    return {
        "tumor_types": _breakdown(conn, "tumor", "tumor_type"),
        "mouse_generations": _breakdown(conn, "mouse", "generation"),
        "assay_types": _breakdown(conn, "assay", "assay_type"),
        "rna_sequenced": (rna, tumor_total),
    }


def oncoprint_svg(matrix: dict[str, Any], max_genes: int = 25, max_samples: int = 120) -> str:
    """Render a gene x sample oncoprint as a self-contained SVG string.

    Cells are colored by mutation status (categorical). Genes are the rows
    (top `max_genes` by frequency); columns are samples carrying at least one
    of those genes, capped at `max_samples` and sorted so similar genotypes sit
    together. Truncation is reported in the returned SVG, never silent.
    """
    cells = matrix["cells"]
    if not cells:
        return (
            '<svg role="img" aria-label="no mutation data" width="360" height="60">'
            '<text x="12" y="34" class="op-empty">No parsed mutation data in this snapshot.</text>'
            "</svg>"
        )

    gene_freq = Counter(g for (g, _s) in cells)
    genes = [g for g, _ in gene_freq.most_common(max_genes)]
    genes_truncated = len(gene_freq) - len(genes)

    all_samples = [s for s in matrix["samples"] if any((g, s) in cells for g in genes)]

    def signature(sample: str) -> tuple:
        return tuple(cells.get((g, sample), "") for g in genes)

    samples = sorted(all_samples, key=signature)
    samples_truncated = max(0, len(samples) - max_samples)
    samples = samples[:max_samples]

    cell, gap, label_w, top = 14, 2, 190, 24
    width = label_w + len(samples) * (cell + gap)
    height = top + len(genes) * (cell + gap) + 8

    parts = [
        f'<svg role="img" aria-label="mutation oncoprint" '
        f'width="{width}" height="{height}" class="oncoprint">',
        f'<text x="12" y="16" class="op-title">Mutations: {len(genes)} genes '
        f"x {len(samples)} samples</text>",
    ]
    for gi, gene in enumerate(genes):
        y = top + gi * (cell + gap)
        parts.append(
            f'<text x="{label_w - 8}" y="{y + cell - 3}" class="op-gene">{escape(gene)}</text>'
        )
        for si, sample in enumerate(samples):
            status = cells.get((gene, sample))
            x = label_w + si * (cell + gap)
            klass = f"op-cell s-{status}" if status else "op-cell s-absent"
            title = f"{gene} · {sample}" + (f" · {status}" if status else "")
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'class="{klass}"><title>{escape(title)}</title></rect>'
            )
    parts.append("</svg>")

    notes = []
    if genes_truncated > 0:
        notes.append(f"{genes_truncated} rarer genes hidden")
    if samples_truncated > 0:
        notes.append(f"{samples_truncated} more samples hidden")
    if notes:
        parts.append(f'<p class="op-note">Showing a subset: {"; ".join(notes)}.</p>')
    return "\n".join(parts)
