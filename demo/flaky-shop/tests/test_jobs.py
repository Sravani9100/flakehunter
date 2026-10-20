import time

from shop.jobs import ExportJob


def test_export_job_starts_pending():
    assert ExportJob().status == "pending"


def test_export_job_completes():
    job = ExportJob()
    job.start()
    time.sleep(0.05)  # long enough on a laptop
    assert job.status == "done"
    assert job.rows == 42
