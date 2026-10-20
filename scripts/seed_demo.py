"""Load demo data: run demo/flaky-shop's test suite repeatedly and ingest the results.

Gives the dashboard realistic history without GitHub. Each simulated CI run is a fresh
pytest process, so the flaky tests really do pass and fail on the same commit.

Usage: python scripts/seed_demo.py [--runs 24]
Then start the API with FLAKEHUNTER_ALLOW_LOCAL_REPOS=true so the AI can work on it.
"""

import argparse
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from flakehunter import models  # noqa: F401  (registers tables)
from flakehunter.config import get_settings
from flakehunter.db import Base, make_engine
from flakehunter.ingest import get_or_create_repo, ingest_reports
from flakehunter.models import utcnow

DEMO_REPO = Path(__file__).resolve().parent.parent / "demo" / "flaky-shop"
REPO_NAME = "demo/flaky-shop"
COMMITS = ["3f9c2ab71d", "8e41d07c5b", "c27a9f13e0"]


def run_suite(report: Path) -> bytes:
    subprocess.run(
        [sys.executable, "-m", "pytest", f"--junitxml={report}", "-q", "-p", "no:cacheprovider"],
        cwd=DEMO_REPO,
        capture_output=True,
        check=False,
    )
    return report.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=24)
    args = parser.parse_args()

    settings = get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    make_session = sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda i: run_suite(Path(tmp) / f"{i}.xml"), range(args.runs)))

    with make_session() as session:
        repo = get_or_create_repo(session, REPO_NAME)
        repo.local_path = str(DEMO_REPO)
        now = utcnow()
        for i, report in enumerate(reports):
            commit = COMMITS[i * len(COMMITS) // len(reports)]
            run = ingest_reports(
                session,
                repo_full_name=REPO_NAME,
                commit_sha=commit,
                reports=[report],
                branch="main",
                ci_run_id=10_000 + i,
            )
            # Spread runs over the past week so the history looks like real CI.
            run.created_at = now - timedelta(hours=(len(reports) - i) * 7)
        session.commit()

    print(f"Ingested {len(reports)} runs into {REPO_NAME} ({settings.database_url}).")


if __name__ == "__main__":
    main()
