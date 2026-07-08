"""Fetch xenograft Content records from SLIMS.

Actual samples live in the ``Content`` table, each linked to its type via
``cntn_fk_contentType`` = a ContentType pk. The pks below come from the
ContentType catalog of this instance.
"""

from collections.abc import Iterator

from slims.criteria import equals
from slims.slims import Slims

# ContentType pk for each entity we care about (from the ContentType catalog).
CONTENT_TYPES = {
    "Mouse": 19,
    "Tumor": 10,
    # Assay-related types from the xenograft data model -- uncomment as needed:
    # "Blood Sample": 21,
    # "Tissue for RNA": 5,
}

# Assay sample types (each becomes an Assay row, keyed by its content type name).
ASSAY_TYPES = {
    "Blood Sample": 21,
    "Tissue for RNA": 5,
}

TUMOR_TYPE = 10
MOUSE_TYPE = 19
TREATMENT_TYPE = 41  # Treatment content, referenced by cntn_cf_fk_treatment

# Default cap so a query against a large instance stays manageable.
DEFAULT_LIMIT = 5

# Page size for full fetches -- SLIMS pages via start/end row indices.
PAGE_SIZE = 1000


def fetch_content(
    slims: Slims, content_type_pk: int, limit: int = DEFAULT_LIMIT
) -> list:
    """Fetch up to `limit` Content records of the given content type."""
    records = slims.fetch(
        "Content",
        equals("cntn_fk_contentType", content_type_pk),
        start=0,
        end=limit,
    )
    return records[:limit]


def fetch_all(
    slims: Slims,
    content_type_pk: int,
    page_size: int = PAGE_SIZE,
    limit: int | None = None,
) -> list:
    """Fetch every Content record of a content type, paging by row index.

    Args:
        content_type_pk: the ContentType pk to filter on.
        page_size: rows per request.
        limit: optional cap on total rows (for quick dev snapshots).
    """
    return list(_iter_content(slims, content_type_pk, page_size, limit))


def _iter_content(
    slims: Slims, content_type_pk: int, page_size: int, limit: int | None
) -> Iterator:
    fetched = 0
    start = 0
    while True:
        end = start + page_size
        if limit is not None:
            end = min(end, limit)
        if end <= start:
            return
        page = slims.fetch(
            "Content",
            equals("cntn_fk_contentType", content_type_pk),
            start=start,
            end=end,
        )
        if not page:
            return
        for record in page:
            yield record
            fetched += 1
            if limit is not None and fetched >= limit:
                return
        if len(page) < (end - start):
            return  # short page => last page
        start = end
