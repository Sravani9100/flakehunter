import hashlib
import hmac
import json

from sqlalchemy import func, select

from flakehunter.models import TestRun
from tests.conftest import WEBHOOK_SECRET, junit


def send(client, event, payload, secret=WEBHOOK_SECRET):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": signature},
    )


def workflow_run(run_attempt=1, action="completed"):
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"full_name": "acme/shop"},
        "workflow_run": {
            "id": 1001,
            "run_attempt": run_attempt,
            "head_sha": "abc1234def",
            "head_branch": "main",
        },
    }


def test_rejects_bad_signature(client):
    assert send(client, "ping", {}, secret="wrong").status_code == 401


def test_ping(client):
    assert send(client, "ping", {"zen": "hi"}).json() == {"status": "pong"}


def test_ignores_other_events(client, fake_github):
    assert send(client, "push", {}).json() == {"status": "ignored"}
    assert send(client, "workflow_run", workflow_run(action="requested")).json() == {
        "status": "ignored"
    }
    assert fake_github.calls == []


def test_rerun_that_passes_is_detected_as_flaky(client, fake_github):
    fake_github.queued = [
        [junit({"test_payment": "failed"}).encode()],
        [junit({"test_payment": "passed"}).encode()],
    ]
    assert send(client, "workflow_run", workflow_run(run_attempt=1)).status_code == 202
    assert send(client, "workflow_run", workflow_run(run_attempt=2)).status_code == 202

    assert fake_github.calls[0] == {
        "installation_id": 42,
        "repo_full_name": "acme/shop",
        "run_id": 1001,
        "name_pattern": r"junit|test-results",
    }
    [flaky] = client.get("/api/repos/acme/shop/flaky-tests").json()
    assert flaky["identifier"] == "tests.test_app::test_payment"


def test_redelivered_webhook_is_not_double_counted(client, fake_github):
    report = [junit({"test_payment": "passed"}).encode()]
    fake_github.queued = [report, report]
    send(client, "workflow_run", workflow_run())
    send(client, "workflow_run", workflow_run())

    with client.app.state.sessionmaker() as session:
        assert session.scalar(select(func.count()).select_from(TestRun)) == 1
