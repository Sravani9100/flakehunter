import asyncio

from fetcher import fetch_all


def test_fetch_all_keeps_input_order():
    assert asyncio.run(fetch_all(["users", "orders"])) == ["users", "orders"]
