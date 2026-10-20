import time

from search import search


def test_search_returns_query():
    started = time.perf_counter()
    results = search("shoes")
    assert results == ["shoes"]
    assert time.perf_counter() - started < 0.05  # "search must be fast"
