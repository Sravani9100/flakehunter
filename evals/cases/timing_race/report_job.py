import random
import threading
import time


class ReportJob:
    def __init__(self) -> None:
        self.status = "pending"

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        time.sleep(random.uniform(0.01, 0.06))  # stands in for variable I/O latency
        self.status = "done"
