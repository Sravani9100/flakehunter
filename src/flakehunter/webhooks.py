import json
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from sqlalchemy.orm import sessionmaker

from flakehunter.github import GitHubClient, verify_signature
from flakehunter.ingest import ingest_reports

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Annotated[str, Header()],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    settings = request.app.state.settings
    if not settings.github_webhook_secret:
        raise HTTPException(503, "Webhooks are disabled: set FLAKEHUNTER_GITHUB_WEBHOOK_SECRET")
    body = await request.body()
    if not verify_signature(settings.github_webhook_secret, body, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")

    payload = json.loads(body)
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "workflow_run" or payload.get("action") != "completed":
        return {"status": "ignored"}

    github: GitHubClient | None = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub App credentials are not configured")

    # Respond fast; GitHub times out webhook deliveries after 10 seconds.
    # TODO: move to a durable job queue so work survives restarts.
    workflow_run = payload["workflow_run"]
    background_tasks.add_task(
        ingest_workflow_run,
        request.app.state.sessionmaker,
        github,
        settings.artifact_name_pattern,
        repo_full_name=payload["repository"]["full_name"],
        installation_id=payload["installation"]["id"],
        run_id=workflow_run["id"],
        run_attempt=workflow_run.get("run_attempt", 1),
        commit_sha=workflow_run["head_sha"],
        branch=workflow_run.get("head_branch"),
    )
    return {"status": "queued"}


def ingest_workflow_run(
    make_session: sessionmaker,
    github: GitHubClient,
    artifact_name_pattern: str,
    *,
    repo_full_name: str,
    installation_id: int,
    run_id: int,
    run_attempt: int,
    commit_sha: str,
    branch: str | None,
) -> None:
    try:
        reports = github.fetch_junit_reports(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            run_id=run_id,
            name_pattern=artifact_name_pattern,
        )
        if not reports:
            log.info("No JUnit artifacts for %s run %s", repo_full_name, run_id)
            return
        with make_session() as session:
            ingest_reports(
                session,
                repo_full_name=repo_full_name,
                commit_sha=commit_sha,
                reports=reports,
                branch=branch,
                ci_run_id=run_id,
                run_attempt=run_attempt,
                source="github",
                installation_id=installation_id,
            )
            session.commit()
    except Exception:
        log.exception("Failed to ingest %s run %s attempt %s", repo_full_name, run_id, run_attempt)
