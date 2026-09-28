from kardinal._core.pagination import Page, iter_all


def _page(items, *, page: int, next_page) -> Page:
    return Page(items=items, page=page, total_pages=2, total=len(items) * 2, next_page=next_page)


def test_iter_all_chains_pages_until_next_page_is_none() -> None:
    pages = {
        1: _page(["a", "b"], page=1, next_page=2),
        2: _page(["c"], page=2, next_page=None),
    }
    result = list(iter_all(lambda page_number: pages[page_number]))
    assert result == ["a", "b", "c"]


def test_iter_all_stops_immediately_on_a_single_page() -> None:
    pages = {1: _page(["only"], page=1, next_page=None)}
    result = list(iter_all(lambda page_number: pages[page_number]))
    assert result == ["only"]


def test_iter_all_respects_start_page() -> None:
    pages = {5: _page(["x"], page=5, next_page=None)}
    result = list(iter_all(lambda page_number: pages[page_number], start_page=5))
    assert result == ["x"]
