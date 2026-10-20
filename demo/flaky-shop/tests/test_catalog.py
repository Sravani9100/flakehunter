from shop.catalog import cart_total, find, tags_for


def test_tags_are_unique():
    products = [{"tags": ["fresh", "dairy"]}, {"tags": ["fresh"]}]
    assert tags_for(products) == ["fresh", "dairy"]


def test_cart_total():
    assert cart_total(["apple", "bread", "milk", "eggs", "apple"]) == 1.3


def test_find_known_product():
    assert find("milk") == 0.3


def test_find_unknown_product():
    assert find("caviar") is None
