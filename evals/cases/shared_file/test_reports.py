import json
import uuid
from pathlib import Path

from reports import build_report, save_report


def test_report_round_trip():
    run_id = uuid.uuid4().hex
    save_report({"run_id": run_id, "status": "pending"})
    save_report(build_report(run_id))
    assert json.loads(Path("report.json").read_text())["run_id"] == run_id
