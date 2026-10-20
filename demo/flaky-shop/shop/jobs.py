import random
import threading
import time


class ExportJob:
    """Exports orders to CSV in the background."""

    def __init__(self) -> None:
        self.status = "pending"
        self.rows = 0

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        time.sleep(random.uniform(0.01, 0.06))  # stands in for database reads
        self.rows = 42
        self.status = "done"
