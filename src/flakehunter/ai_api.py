"""Endpoints that call the model or run the fix agent."""

import json
import logging
import re
from typing import Any

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from flakehunter.api import SessionDep, get_repo, get_test
from flakehunter.context import build_context
from flakehunter.diagnosis import ThinkingDelta, run_diagnosis
from flakehunter.fixes import latest_commit, run_fix_attempt
from flakehunter.llm import describe_error, make_client
from flakehunter.models import FixAttempt, FixStatus, Repository, TestCase
from flakehunter.schemas import DiagnosisOut, FixAttemptOut, FixAttemptSummary
from flakehunter.testloc import locate_test
from flakehunter.workspace import checkout

log = logging.getLogger(__name__)


def require_ai(request: Request) -> None:
    if not request.app.state.settings.ai_enabled:
        raise HTTPException(403, "AI features are disabled on this server")


router = APIRouter(prefix="/api")
AI = [Depends(require_ai)]


def get_llm(request: Request) -> Any:
    if request.app.state.llm is None:
        try:
            request.app.state.llm = make_client(request.app.state.settings)
        except anthropic.AnthropicError as exc:
            raise HTTPException(503, "Anthropic credentials are not configured") from exc
    return request.app.state.llm


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/repos/{owner}/{repo}/tests/{test_id}/diagnose", dependencies=AI)
def diagnose(
    owner: str, repo: str, test_id: int, request: Request, session: SessionDep
) -> StreamingResponse:
    """Stream the model's reasoning as server-sent events, then the saved diagnosis."""
    repo_id = get_repo(session, owner, repo).id
    get_test(session, session.get(Repository, repo_id), test_id)
    commit = latest_commit(session, test_id)
    client = get_llm(request)
    state = request.app.state

    def events():
        try:
            yield _sse("status", {"message": "Checking out the code"})
            with state.sessionmaker() as s:
                repository, test_case = s.get(Repository, repo_id), s.get(TestCase, test_id)
                with checkout(repository, commit, state.github, state.settings) as workspace:
                    location = locate_test(workspace, test_case.identifier, test_case.file)
                    context = build_context(s, test_case, workspace, location)
                yield _sse("status", {"message": "Analyzing"})
                for item in run_diagnosis(client, state.settings, test_id, context):
                    if isinstance(item, ThinkingDelta):
                        yield _sse("thinking", {"text": item.text})
                    else:
                        s.add(item)
                        s.commit()
                        result = DiagnosisOut.model_validate(item)
                        yield _sse("result", result.model_dump(mode="json"))
        except Exception as exc:
            log.exception("Diagnosis of test %s failed", test_id)
            yield _sse("error", {"message": describe_error(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/repos/{owner}/{repo}/tests/{test_id}/fix", status_code=202, dependencies=AI)
def start_fix(
    owner: str,
    repo: str,
    test_id: int,
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> FixAttemptSummary:
    test_case = get_test(session, get_repo(session, owner, repo), test_id)
    active = session.scalar(
        select(FixAttempt).where(
            FixAttempt.test_case_id == test_case.id,
            FixAttempt.status.in_([FixStatus.QUEUED, FixStatus.RUNNING]),
        )
    )
    if active is not None:
        raise HTTPException(409, f"Fix attempt {active.id} is already in progress")
    commit = latest_commit(session, test_case.id)
    if commit is None:
        raise HTTPException(422, "This test has no recorded runs")

    client = get_llm(request)
    attempt = FixAttempt(test_case_id=test_case.id, commit_sha=commit)
    session.add(attempt)
    session.commit()

    state = request.app.state
    # TODO: move to a durable job queue so attempts survive restarts.
    background_tasks.add_task(
        run_fix_attempt,
        state.sessionmaker,
        attempt.id,
        client=client,
        settings=state.settings,
        sandbox=state.sandbox,
        github=state.github,
    )
    return FixAttemptSummary.model_validate(attempt)


def _can_open_pr(request: Request, attempt: FixAttempt, repo: Repository) -> bool:
    return (
        attempt.status == FixStatus.VERIFIED
        and attempt.pr_url is None
        and request.app.state.github is not None
        and repo.installation_id is not None
    )


def _attempt_out(request: Request, attempt: FixAttempt, repo: Repository) -> FixAttemptOut:
    return FixAttemptOut(
        **FixAttemptSummary.model_validate(attempt).model_dump(),
        test_case_id=attempt.test_case_id,
        repo=repo.full_name,
        test_identifier=attempt.test_case.identifier,
        explanation=attempt.explanation,
        diff=attempt.diff,
        integrity_issues=attempt.integrity_issues or [],
        review_notes=attempt.review_notes or [],
        model=attempt.model,
        input_tokens=attempt.input_tokens,
        output_tokens=attempt.output_tokens,
        error=attempt.error,
        can_open_pr=_can_open_pr(request, attempt, repo),
        steps=attempt.steps,
    )


def _load_attempt(session, attempt_id: int) -> tuple[FixAttempt, Repository]:
    attempt = session.get(FixAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, "Fix attempt not found")
    return attempt, session.get(Repository, attempt.test_case.repo_id)


@router.get("/fix-attempts/{attempt_id}")
def get_fix_attempt(attempt_id: int, request: Request, session: SessionDep) -> FixAttemptOut:
    attempt, repo = _load_attempt(session, attempt_id)
    return _attempt_out(request, attempt, repo)


@router.post("/fix-attempts/{attempt_id}/pull-request", dependencies=AI)
def open_pull_request(attempt_id: int, request: Request, session: SessionDep) -> FixAttemptOut:
    attempt, repo = _load_attempt(session, attempt_id)
    if not _can_open_pr(request, attempt, repo):
        raise HTTPException(
            409, "Only verified fixes on GitHub App repositories can open a pull request"
        )
    test_name = attempt.test_case.identifier.rpartition("::")[2]
    slug = re.sub(r"[^a-z0-9]+", "-", test_name.lower()).strip("-")[:40]
    attempt.pr_url = request.app.state.github.open_pull_request(
        installation_id=repo.installation_id,
        repo_full_name=repo.full_name,
        base_sha=attempt.commit_sha,
        branch=f"flakehunter/{slug}-{attempt.id}",
        files=attempt.files or {},
        title=f"Fix flaky test {test_name}",
        body=pr_body(attempt),
    )
    session.commit()
    return _attempt_out(request, attempt, repo)


def pr_body(attempt: FixAttempt) -> str:
    lines = [attempt.explanation or "", "", "### Verification", ""]
    if attempt.baseline_runs:
        lines.append(
            f"- Before: failed {attempt.baseline_failures} of {attempt.baseline_runs} "
            "fresh-process runs"
        )
    lines.append(
        f"- After: passed {attempt.verification_runs - attempt.verification_failures} of "
        f"{attempt.verification_runs} fresh-process runs"
    )
    if attempt.review_notes:
        lines += ["", "### Please check", "", *[f"- {note}" for note in attempt.review_notes]]
    lines += ["", f"_Opened by FlakeHunter. Root cause category: {attempt.category}._"]
    return "\n".join(lines)
