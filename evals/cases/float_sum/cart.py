PRICES = {"apple": 0.1, "bread": 0.2, "milk": 0.3, "eggs": 0.7}


def cart_total(items: list[str]) -> float:
    total = 0.0
    for item in set(items):  # each distinct item is charged once
        total += PRICES[item]
    return total
