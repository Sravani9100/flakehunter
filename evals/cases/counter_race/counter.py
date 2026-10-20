import random
import time


class HitCounter:
    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> None:
        current = self.value
        if random.random() < 0.002:
            time.sleep(0.0001)  # stands in for occasional slow I/O (metrics flush)
        self.value = current + 1
