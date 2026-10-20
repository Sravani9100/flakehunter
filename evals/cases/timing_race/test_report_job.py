import time

from report_job import ReportJob


def test_report_job_completes():
    job = ReportJob()
    job.start()
    time.sleep(0.05)  # "long enough" on the author's laptop
    assert job.status == "done"
