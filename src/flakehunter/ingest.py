"""Turn JUnit reports into TestRun and TestResult rows."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from flakehunter.junit import ParsedCase, parse_junit
from flakehunter.models import Repository, TestCase, TestResult, TestRun


def get_or_create_repo(
    session: Session, full_name: str, installation_id: int | None = None
) -> Repository:
    repo = session.scalar(select(Repository).where(Repository.full_name == full_name))
    if repo is None:
        repo = Repository(full_name=full_name)
        session.add(repo)
    if installation_id is not None:
        repo.installation_id = installation_id
    session.flush()
    return repo


def ingest_reports(
    session: Session,
    *,
    repo_full_name: str,
    commit_sha: str,
    reports: Iterable[bytes | str],
    branch: str | None = None,
    ci_run_id: int | None = None,
    run_attempt: int = 1,
    source: str = "upload",
    installation_id: int | None = None,
) -> TestRun:
    """Store one CI run's reports. Redelivering the same (ci_run_id, run_attempt) is a no-op."""
    # Parse everything first so a bad report doesn't leave a partial run behind.
    cases = [case for report in reports for case in parse_junit(report)]

    repo = get_or_create_repo(session, repo_full_name, installation_id)
    if ci_run_id is not None:
        existing = session.scalar(
            select(TestRun).where(
                TestRun.repo_id == repo.id,
                TestRun.ci_run_id == ci_run_id,
                TestRun.run_attempt == run_attempt,
            )
        )
        if existing is not None:
            return existing

    run = TestRun(
        repo_id=repo.id,
        commit_sha=commit_sha.lower(),
        branch=branch,
        ci_run_id=ci_run_id,
        run_attempt=run_attempt,
        source=source,
    )
    session.add(run)
    test_cases = _upsert_test_cases(session, repo.id, cases)
    session.add_all(
        TestResult(
            run=run,
            test_case=test_cases[case.identifier],
            outcome=case.outcome,
            duration_s=case.duration_s,
            message=case.message,
            details=case.details,
        )
        for case in cases
    )
    session.flush()
    return run


def _upsert_test_cases(
    session: Session, repo_id: int, cases: list[ParsedCase]
) -> dict[str, TestCase]:
    files = {case.identifier: case.file for case in cases}
    existing = {
        tc.identifier: tc
        for tc in session.scalars(
            select(TestCase).where(
                TestCase.repo_id == repo_id, TestCase.identifier.in_(list(files))
            )
        )
    }
    for identifier, file in files.items():
        if identifier not in existing:
            existing[identifier] = TestCase(repo_id=repo_id, identifier=identifier, file=file)
            session.add(existing[identifier])
    return existing
