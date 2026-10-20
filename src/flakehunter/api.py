import hmac
import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flakehunter.detection import ResultRow, compute_flake_stats, rank_flaky
from flakehunter.ingest import get_or_create_repo, ingest_reports
from flakehunter.junit import JUnitParseError
from flakehunter.models import (
    Diagnosis,
    FixAttempt,
    Outcome,
    Repository,
    TestCase,
    TestResult,
    TestRun,
    utcnow,
)
from flakehunter.schemas import (
    DiagnosisOut,
    FixAttemptSummary,
    FlakyTestOut,
    RepoCreate,
    RepoOut,
    ResultOut,
    RunOut,
    StatsOut,
    TestDetailOut,
)

router = APIRouter(prefix="/api")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


def require_upload_token(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    expected = request.app.state.settings.upload_token
    if not expected:
        raise HTTPException(503, "Uploads are disabled: set FLAKEHUNTER_UPLOAD_TOKEN")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, "Invalid upload token")


SessionDep = Annotated[Session, Depends(get_session)]


def get_repo(session: Session, owner: str, repo: str) -> Repository:
    repository = session.scalar(select(Repository).where(Repository.full_name == f"{owner}/{repo}"))
    if repository is None:
        raise HTTPException(404, "Repository not found")
    return repository


def get_test(session: Session, repository: Repository, test_id: int) -> TestCase:
    test_case = session.get(TestCase, test_id)
    if test_case is None or test_case.repo_id != repository.id:
        raise HTTPException(404, "Test not found")
    return test_case


def _result_rows(session: Session, repo_id: int, cutoff=None):
    query = (
        select(TestResult.test_case_id, TestRun.commit_sha, TestResult.outcome, TestRun.created_at)
        .join(TestRun)
        .where(TestRun.repo_id == repo_id)
    )
    if cutoff is not None:
        query = query.where(TestRun.created_at >= cutoff)
    return [ResultRow(*row) for row in session.execute(query)]


def _cutoff(request: Request, days: int | None = None):
    return utcnow() - timedelta(days=days or request.app.state.settings.flake_window_days)


@router.get("/evals/latest")
def latest_evals(request: Request) -> dict:
    path = request.app.state.settings.evals_results_path
    if not path.is_file():
        raise HTTPException(404, "No eval results yet: run python evals/run_evals.py")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/repos")
def list_repos(request: Request, session: SessionDep) -> list[RepoOut]:
    repos = []
    for repo in session.scalars(select(Repository).order_by(Repository.full_name)):
        total_runs, last_run_at = session.execute(
            select(func.count(TestRun.id), func.max(TestRun.created_at)).where(
                TestRun.repo_id == repo.id
            )
        ).one()
        stats = compute_flake_stats(_result_rows(session, repo.id, _cutoff(request)))
        if repo.local_path:
            source = "local"
        elif repo.installation_id:
            source = "github"
        else:
            source = "upload"
        repos.append(
            RepoOut(
                full_name=repo.full_name,
                source=source,
                flaky_tests=sum(1 for s in stats.values() if s.is_flaky),
                total_runs=total_runs,
                last_run_at=last_run_at,
            )
        )
    return repos


@router.post("/repos", status_code=201)
def register_local_repo(body: RepoCreate, request: Request, session: SessionDep) -> RepoOut:
    """Dev only: point a repository at a local checkout so the AI can work on it."""
    if not request.app.state.settings.allow_local_repos:
        raise HTTPException(403, "Local repositories are disabled")
    path = Path(body.local_path).resolve()
    if not path.is_dir():
        raise HTTPException(422, "local_path is not a directory")
    repo = get_or_create_repo(session, body.full_name)
    repo.local_path = str(path)
    session.commit()
    return RepoOut(
        full_name=repo.full_name, source="local", flaky_tests=0, total_runs=0, last_run_at=None
    )


@router.post(
    "/repos/{owner}/{repo}/runs",
    status_code=201,
    dependencies=[Depends(require_upload_token)],
)
def upload_run(
    owner: str,
    repo: str,
    session: SessionDep,
    commit_sha: Annotated[str, Form(pattern=r"^[0-9a-fA-F]{7,40}$")],
    files: Annotated[list[UploadFile], File()],
    branch: Annotated[str | None, Form()] = None,
    ci_run_id: Annotated[int | None, Form()] = None,
    run_attempt: Annotated[int, Form(ge=1)] = 1,
) -> RunOut:
    """Upload JUnit reports from one CI run. Use this from CI without installing the App."""
    try:
        run = ingest_reports(
            session,
            repo_full_name=f"{owner}/{repo}",
            commit_sha=commit_sha,
            reports=[f.file.read() for f in files],
            branch=branch,
            ci_run_id=ci_run_id,
            run_attempt=run_attempt,
        )
    except JUnitParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return RunOut(
        id=run.id, commit_sha=run.commit_sha, run_attempt=run.run_attempt, results=len(run.results)
    )


@router.get("/repos/{owner}/{repo}/flaky-tests")
def list_flaky_tests(
    owner: str,
    repo: str,
    request: Request,
    session: SessionDep,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
) -> list[FlakyTestOut]:
    repository = get_repo(session, owner, repo)
    rows = _result_rows(session, repository.id, _cutoff(request, days))
    ranked = rank_flaky(compute_flake_stats(rows))

    cases = {
        tc.id: tc
        for tc in session.scalars(
            select(TestCase).where(TestCase.id.in_([s.test_case_id for s in ranked]))
        )
    }
    return [
        FlakyTestOut(
            id=s.test_case_id,
            identifier=cases[s.test_case_id].identifier,
            file=cases[s.test_case_id].file,
            runs=s.runs,
            failures=s.failures,
            fail_rate=round(s.fail_rate, 4),
            flaky_commits=s.flaky_commits,
            last_flake_at=s.last_flake_at,
        )
        for s in ranked
    ]


def _results(session: Session, test_id: int, limit: int) -> list[ResultOut]:
    rows = session.execute(
        select(TestResult, TestRun)
        .join(TestRun)
        .where(TestResult.test_case_id == test_id)
        .order_by(TestRun.created_at.desc(), TestResult.id.desc())
        .limit(limit)
    ).all()
    return [
        ResultOut(
            run_id=run.id,
            commit_sha=run.commit_sha,
            branch=run.branch,
            run_attempt=run.run_attempt,
            outcome=result.outcome,
            duration_s=result.duration_s,
            message=result.message,
            details=result.details,
            recorded_at=run.created_at,
        )
        for result, run in rows
    ]


@router.get("/repos/{owner}/{repo}/tests/{test_id}/results")
def list_test_results(
    owner: str,
    repo: str,
    test_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[ResultOut]:
    get_test(session, get_repo(session, owner, repo), test_id)
    return _results(session, test_id, limit)


@router.get("/repos/{owner}/{repo}/tests/{test_id}")
def get_test_detail(
    owner: str, repo: str, test_id: int, request: Request, session: SessionDep
) -> TestDetailOut:
    repository = get_repo(session, owner, repo)
    test_case = get_test(session, repository, test_id)

    rows = [r for r in _result_rows(session, repository.id) if r.test_case_id == test_id]
    stats = compute_flake_stats(rows).get(test_id)
    history = _results(session, test_id, 60)
    latest_failure = next(
        (r for r in history if r.outcome in (Outcome.FAILED, Outcome.ERROR)), None
    )
    diagnosis = session.scalar(
        select(Diagnosis)
        .where(Diagnosis.test_case_id == test_id)
        .order_by(Diagnosis.created_at.desc())
        .limit(1)
    )
    attempts = session.scalars(
        select(FixAttempt)
        .where(FixAttempt.test_case_id == test_id)
        .order_by(FixAttempt.created_at.desc())
    )
    return TestDetailOut(
        id=test_case.id,
        repo=repository.full_name,
        identifier=test_case.identifier,
        file=test_case.file,
        stats=StatsOut(
            runs=stats.runs,
            failures=stats.failures,
            fail_rate=round(stats.fail_rate, 4),
            flaky_commits=stats.flaky_commits,
            last_flake_at=stats.last_flake_at,
        )
        if stats
        else None,
        latest_failure=latest_failure,
        history=history,
        diagnosis=DiagnosisOut.model_validate(diagnosis) if diagnosis else None,
        fix_attempts=[FixAttemptSummary.model_validate(a) for a in attempts],
        ai_enabled=request.app.state.settings.ai_enabled,
    )
