"""Generic pagination wrapper.

openapi.yaml only skips pagination when *both* `page` and `itemsPerPage`
are absent from the request, so the SDK always sends both explicitly, even
when the caller passes neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class Page(Generic[T]):
    """One page of a paginated collection. `next_page` is `None` on the
    last page, `previous_page` on the first; asking for a page past the
    last one returns the last page.
    """

    items: List[T]
    page: int
    total_pages: int
    total: int
    next_page: Optional[int]
    # Absent on the first page (`next_page` is absent on the last one).
    previous_page: Optional[int] = None
    items_per_page: Optional[int] = None


def iter_all(fetch_page: Callable[[int], "Page[T]"], *, start_page: int = 1) -> Iterator[T]:
    """Chain pages transparently, yielding items one at a time."""
    page_number = start_page
    while True:
        page = fetch_page(page_number)
        yield from page.items
        if page.next_page is None:
            return
        page_number = page.next_page
