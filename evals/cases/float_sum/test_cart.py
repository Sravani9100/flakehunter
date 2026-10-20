from cart import cart_total


def test_cart_total_charges_each_item_once():
    assert cart_total(["apple", "bread", "milk", "eggs", "apple"]) == 1.3
