"""Fetch xenograft Content records from SLIMS.

Actual samples live in the ``Content`` table, each linked to its type via
its name (`cntp_name`).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from itertools import batched
from typing import Any, Sequence

from slims.criteria import equals, is_one_of, conjunction, is_not_one_of
from slims.slims import Slims
from .slims_spec import TableSpec, CONTENT
from .content_types import TUMOR_TYPES

logger = logging.getLogger(__name__)


# Page size for full fetches -- SLIMS pages via start/end row indices.
PAGE_SIZE = 1000
BATCH_SIZE = 200


def paged_fetch(
    slims: Slims,
    table: str,
    table_key: str,
    keys: list[int],
) -> Iterator[Any]:
    """Yield every record matching pks with paging to avoid overloading SLIMS.
    """
    start = 0
    assert PAGE_SIZE > 0
    end = start + PAGE_SIZE
    while start < end:
        criterion = is_one_of(table_key, keys)
        page = slims.fetch(table, criterion, start=start, end=end)
        if len(page) == 0:
            return
        yield from page
        if len(page) < PAGE_SIZE:
            return
        start = end
        end = start + PAGE_SIZE


def fetch_project(
    slims: Slims,
    project_name: str,
) -> Any:
    """Resolve a Project by name (`prjc_name`).

    Expects one project entry per project name. Raises error if not exactly one is found.
    """
    projects = slims.fetch("Project", equals("prjc_name", project_name))
    if len(projects) != 1:
        raise ValueError(f"Expected one project named {project_name!r}, got {len(projects)}")
    return projects[0]


def fetch_by_parents(
    slims: Slims,
    spec: TableSpec,
    parent_pks: Sequence[int],
    batch_size: int = BATCH_SIZE,
    limit: int | None = None,
) -> Iterator[list[Any]]:
    """All rows of SLIMS table whose parent fk is one of `parent_pks`.

    Fetch by batches on pk list to avoid failed queries.
    """
    if spec.parent_fk is None:
        raise ValueError(f"{spec.table} has no parent_fk configured")
    if not parent_pks:
        return
    pks = sorted({int(p) for p in parent_pks})
    total_fetched = 0
    for batch in batched(pks, batch_size):
        fetched = list(paged_fetch(slims, spec.table, spec.parent_fk, list(batch)))
        total_fetched += len(fetched)
        yield fetched
        if limit is not None and total_fetched >= limit:
            return


def fetch_content_by_mammoid(
    slims: Slims,
    mammoids: Sequence[str],
    batch_size: int = BATCH_SIZE,
    limit: int | None= None,
) -> Iterator[list[Any]]:
    if not mammoids:
        return
    total_fetched = 0
    for batch in batched(mammoids, batch_size):
        criteria = conjunction()
        if CONTENT.name:
            criteria.add(is_one_of(CONTENT.name, TUMOR_TYPES))
        if CONTENT.mammoid:
            criteria.add(is_one_of(CONTENT.mammoid, list(batch)))
        fetched = slims.fetch(CONTENT.table, criteria)
        total_fetched += len(fetched)
        yield fetched
        if limit is not None and total_fetched >= limit:
            return


def fetch_content_by_pk(
    slims: Slims,
    content_pks: set[int],
    batch_size: int = BATCH_SIZE,
    limit: int | None = None,
) -> Iterator[list[Any]]:
    """Yield Content records in batches.

    The caller can commit as it goes and resume after an interruption
    instead of restarting the whole fetch. No need to page as there is
    a one-to-one correspondence between pks and records. Batching already
    handles the paging.
    """
    if not content_pks:
        return
    pks = sorted({int(p) for p in content_pks})
    total_fetched = 0
    for batch in batched(pks, batch_size):
        criteria = conjunction()
        criteria.add(is_one_of(CONTENT.pk, list(batch)))
        if CONTENT.name:
            criteria.add(is_not_one_of(CONTENT.name, TUMOR_TYPES))
        fetched = slims.fetch(CONTENT.table, criteria)
        total_fetched += len(fetched)
        yield fetched
        if limit is not None and total_fetched >= limit:
            return
