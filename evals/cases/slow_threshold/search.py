import random
import time


def search(query: str) -> list[str]:
    time.sleep(random.uniform(0.02, 0.06))  # stands in for an index lookup
    return [query]
