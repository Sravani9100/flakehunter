"""Run a fix attempt end to end: checkout, reproduce, agent, verify, integrity check."""

import difflib
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flakehunter.agent import FixAgent, Step
from flakehunter.config import Settings
from flakehunter.context import build_context
from flakehunter.github import GitHubClient
from flakehunter.integrity import check_integrity
from flakehunter.llm import describe_error
from flakehunter.models import (
    AgentStep,
    Diagnosis,
    FixAttempt,
    FixStatus,
    Repository,
    TestCase,
    TestResult,
    TestRun,
    utcnow,
)
from flakehunter.sandbox import Sandbox
from flakehunter.testloc import locate_test
from flakehunter.workspace import checkout

log = logging.getLogger(__name__)


def latest_commit(session: Session, test_case_id: int) -> str | None:
    return session.scalar(
        select(TestRun.commit_sha)
        .join(TestResult)
        .where(TestResult.test_case_id == test_case_id)
        .order_by(TestRun.created_at.desc())
        .limit(1)
    )


def run_fix_attempt(
    make_session: sessionmaker,
    attempt_id: int,
    *,
    client: Any,
    settings: Settings,
    sandbox: Sandbox,
    github: GitHubClient | None,
) -> None:
    started = time.monotonic()
    with make_session() as session:
        attempt = session.get(FixAttempt, attempt_id)
        test_case = session.get(TestCase, attempt.test_case_id)
        repo = session.get(Repository, test_case.repo_id)
        attempt.status = FixStatus.RUNNING
        session.commit()

        def record(step: Step) -> None:
            # Commit each step so the dashboard can show the trace while the agent works.
            session.add(
                AgentStep(
                    fix_attempt_id=attempt.id,
                    index=len(attempt.steps),
                    kind=step.kind,
                    tool=step.tool,
                    input=step.input,
                    output=step.output,
                    is_error=step.is_error,
                    duration_s=step.duration_s,
                )
            )
            session.commit()
            session.refresh(attempt, ["steps"])

        try:
            with checkout(repo, attempt.commit_sha, github, settings) as workspace:
                location = locate_test(workspace, test_case.identifier, test_case.file)
                baseline = sandbox.run_test(workspace, location.node_id, settings.baseline_runs)
                attempt.baseline_runs, attempt.baseline_failures = baseline.runs, baseline.failures
                session.commit()

                context = build_context(session, test_case, workspace, location, baseline)
                context += _previous_diagnosis(session, test_case.id)
                agent = FixAgent(client, settings, sandbox, on_step=record)
                result = agent.run(workspace, location, context)

                attempt.model = result.model
                attempt.input_tokens = result.usage.input_tokens
                attempt.output_tokens = result.usage.output_tokens
                attempt.cost_usd = result.usage.cost_usd
                attempt.category = result.category
                attempt.explanation = result.explanation

                changed = {
                    path: content
                    for path, content in result.changed_files.items()
                    if content != result.original_files.get(path)
                }
                if not changed:
                    attempt.status = FixStatus.NOT_FIXED
                else:
                    attempt.files = changed
                    attempt.diff = make_diff(result.original_files, changed)
                    integrity = check_integrity(result.original_files, changed, location)
                    attempt.integrity_issues = integrity.issues
                    attempt.review_notes = integrity.notes
                    verification = sandbox.run_test(
                        workspace, location.node_id, settings.verify_runs
                    )
                    attempt.verification_runs = verification.runs
                    attempt.verification_failures = verification.failures
                    if integrity.issues:
                        attempt.status = FixStatus.REJECTED
                    elif verification.failures == 0:
                        attempt.status = FixStatus.VERIFIED
                    else:
                        attempt.status = FixStatus.NOT_FIXED
        except Exception as exc:
            log.exception("Fix attempt %s failed", attempt_id)
            attempt.status = FixStatus.ERROR
            attempt.error = describe_error(exc)
        finally:
            attempt.duration_s = time.monotonic() - started
            attempt.finished_at = utcnow()
            session.commit()


def make_diff(original: dict[str, str], changed: dict[str, str]) -> str:
    chunks = []
    for path in sorted(changed):
        chunks.extend(
            difflib.unified_diff(
                original.get(path, "").splitlines(keepends=True),
                changed[path].splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    return "".join(chunks)


def _previous_diagnosis(session: Session, test_case_id: int) -> str:
    diagnosis = session.scalar(
        select(Diagnosis)
        .where(Diagnosis.test_case_id == test_case_id)
        .order_by(Diagnosis.created_at.desc())
        .limit(1)
    )
    if diagnosis is None:
        return ""
    return (
        "\n\n## Earlier diagnosis (verify it; it may be wrong)\n\n"
        f"Category: {diagnosis.category} (confidence {diagnosis.confidence:.0%})\n\n"
        f"{diagnosis.explanation}\n\nSuggested fix: {diagnosis.suggested_fix}"
    )
