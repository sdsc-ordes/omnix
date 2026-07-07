"""Fetch xenograft Content records from SLIMS.

Actual samples live in the ``Content`` table, each linked to its type via
``cntn_fk_contentType`` = a ContentType pk. The pks below come from the
ContentType catalog of this instance.
"""

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

# Default cap so a query against a large instance stays manageable.
DEFAULT_LIMIT = 5


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
