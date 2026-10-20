import json
import time
from pathlib import Path


def save_report(data: dict, path: Path = Path("report.json")) -> None:
    path.write_text(json.dumps(data))


def build_report(run_id: str) -> dict:
    time.sleep(0.02)  # stands in for rendering
    return {"run_id": run_id, "status": "ok"}
