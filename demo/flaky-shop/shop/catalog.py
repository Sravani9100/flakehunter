PRICES = {"apple": 0.1, "bread": 0.2, "milk": 0.3, "eggs": 0.7}


def tags_for(products: list[dict]) -> list[str]:
    tags = set()
    for product in products:
        tags.update(product["tags"])
    return list(tags)


def cart_total(items: list[str]) -> float:
    total = 0.0
    for item in set(items):  # each distinct item is charged once
        total += PRICES[item]
    return total


def find(name: str) -> float | None:
    return PRICES.get(name)
