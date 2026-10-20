import json

import pytest

from flakehunter.models import FixAttempt, FixStatus, Repository
from tests.conftest import UPLOAD_TOKEN, junit
from tests.fakes import make_repo, message, text, tool_use

AUTH = {"Authorization": f"Bearer {UPLOAD_TOKEN}"}
DIAGNOSIS = {
    "category": "randomness",
    "confidence": 0.9,
    "summary": "ready() is random.",
    "explanation": "It returns True half the time.",
    "evidence": ["return random.random() > 0.5"],
    "suggested_fix": "Make readiness deterministic.",
}
FIXED_TEST = "def test_ready():\n    assert ready()  # FIXED\n"


@pytest.fixture
def test_id(client, tmp_path):
    repo = make_repo(tmp_path / "repo")
    assert (
        client.post(
            "/api/repos", json={"full_name": "acme/shop", "local_path": str(repo)}
        ).status_code
        == 201
    )
    for outcome in ("passed", "failed"):
        client.post(
            "/api/repos/acme/shop/runs",
            data={"commit_sha": "abc1234"},
            files=[("files", ("r.xml", junit({"test_ready": outcome}, "tests.test_clock")))],
            headers=AUTH,
        )
    [flaky] = client.get("/api/repos/acme/shop/flaky-tests").json()
    return flaky["id"]


def sse_events(response):
    events = []
    for chunk in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def fix_script(edit_new_str=FIXED_TEST, fixed=True):
    return [
        message(tool_use("run_test", runs=10)),
        message(
            tool_use(
                "edit_file",
                path="tests/test_clock.py",
                old_str="def test_ready():\n    assert ready()\n",
                new_str=edit_new_str,
            )
        ),
        message(
            text("Done."),
            tool_use("submit_fix", fixed=fixed, category="randomness", explanation="**Seeded.**"),
        ),
    ]


def test_repos_listing(client, test_id):
    [repo] = client.get("/api/repos").json()
    assert repo == {**repo, "full_name": "acme/shop", "source": "local", "flaky_tests": 1}
    assert repo["total_runs"] == 2


def test_local_repos_can_be_disabled(client, settings, tmp_path):
    settings.allow_local_repos = False
    response = client.post("/api/repos", json={"full_name": "a/b", "local_path": str(tmp_path)})
    assert response.status_code == 403


def test_diagnosis_streams_thinking_then_saves_result(client, fake_llm, test_id):
    fake_llm.script_diagnosis(DIAGNOSIS, thoughts=("Reading ", "the code."))
    response = client.post(f"/api/repos/acme/shop/tests/{test_id}/diagnose")
    events = sse_events(response)

    assert [e for e, _ in events] == ["status", "status", "thinking", "thinking", "result"]
    result = events[-1][1]
    assert result["category"] == "randomness"
    assert result["thinking"] == "Reading the code."
    assert result["cost_usd"] > 0

    # The model saw the test source and the module under test.
    prompt = fake_llm.messages.requests[0]["messages"][0]["content"]
    assert "### `tests/test_clock.py`" in prompt and "### `app/clock.py`" in prompt
    assert "1 failures in 2 runs" in prompt

    detail = client.get(f"/api/repos/acme/shop/tests/{test_id}").json()
    assert detail["diagnosis"]["summary"] == "ready() is random."
    assert detail["stats"]["flaky_commits"] == 1


def test_diagnosis_refusal_becomes_error_event(client, fake_llm, test_id):
    fake_llm.script_diagnosis(DIAGNOSIS)
    fake_llm.messages.stream_script[1].stop_reason = "refusal"
    events = sse_events(client.post(f"/api/repos/acme/shop/tests/{test_id}/diagnose"))
    assert events[-1][0] == "error"
    assert "declined" in events[-1][1]["message"]


def test_verified_fix(client, fake_llm, fake_sandbox, test_id):
    fake_llm.messages.responses = fix_script()
    started = client.post(f"/api/repos/acme/shop/tests/{test_id}/fix")
    assert started.status_code == 202

    attempt = client.get(f"/api/fix-attempts/{started.json()['id']}").json()
    assert attempt["status"] == "verified", attempt["error"]
    assert (attempt["baseline_runs"], attempt["baseline_failures"]) == (20, 10)
    assert (attempt["verification_runs"], attempt["verification_failures"]) == (100, 0)
    assert "+    assert ready()  # FIXED" in attempt["diff"]
    assert attempt["explanation"] == "**Seeded.**"
    assert [s["tool"] for s in attempt["steps"] if s["kind"] == "tool"] == [
        "run_test", "edit_file", "submit_fix",
    ]  # fmt: skip
    assert attempt["cost_usd"] > 0
    assert attempt["can_open_pr"] is False  # local repo, no GitHub App installation


def test_skip_marker_fix_is_rejected(client, fake_llm, test_id):
    gamed = "import pytest\n\n@pytest.mark.skip\ndef test_ready():\n    assert ready()  # FIXED\n"
    fake_llm.messages.responses = fix_script(edit_new_str=gamed)
    attempt_id = client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").json()["id"]
    attempt = client.get(f"/api/fix-attempts/{attempt_id}").json()
    assert attempt["status"] == "rejected"
    assert attempt["integrity_issues"]


def test_agent_that_changes_nothing_is_not_fixed(client, fake_llm, test_id):
    fake_llm.messages.responses = [
        message(tool_use("submit_fix", fixed=False, category="unknown", explanation="No idea."))
    ]
    attempt_id = client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").json()["id"]
    assert client.get(f"/api/fix-attempts/{attempt_id}").json()["status"] == "not_fixed"


def test_agent_crash_is_recorded(client, fake_llm, test_id):
    fake_llm.messages.responses = []  # the fake raises IndexError on the first call
    attempt_id = client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").json()["id"]
    attempt = client.get(f"/api/fix-attempts/{attempt_id}").json()
    assert attempt["status"] == "error"
    assert attempt["finished_at"] is not None


def test_one_attempt_at_a_time(client, test_id):
    with client.app.state.sessionmaker() as session:
        session.add(
            FixAttempt(test_case_id=test_id, commit_sha="abc1234", status=FixStatus.RUNNING)
        )
        session.commit()
    assert client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").status_code == 409


def test_open_pull_request_for_verified_fix(client, fake_llm, fake_github, test_id):
    with client.app.state.sessionmaker() as session:
        session.query(Repository).one().installation_id = 42
        session.commit()
    fake_llm.messages.responses = fix_script()
    attempt_id = client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").json()["id"]
    assert client.get(f"/api/fix-attempts/{attempt_id}").json()["can_open_pr"] is True

    attempt = client.post(f"/api/fix-attempts/{attempt_id}/pull-request").json()
    assert attempt["pr_url"] == "https://github.com/acme/shop/pull/7"
    [pr] = fake_github.pull_requests
    assert pr["base_sha"] == "abc1234"
    assert pr["branch"] == f"flakehunter/test-ready-{attempt_id}"
    assert pr["files"]["tests/test_clock.py"].endswith(FIXED_TEST)
    assert "passed 100 of 100" in pr["body"]
    # A second PR for the same fix is refused.
    assert client.post(f"/api/fix-attempts/{attempt_id}/pull-request").status_code == 409


def test_ai_can_be_disabled(client, settings, test_id):
    settings.ai_enabled = False
    assert client.post(f"/api/repos/acme/shop/tests/{test_id}/fix").status_code == 403
    assert client.post(f"/api/repos/acme/shop/tests/{test_id}/diagnose").status_code == 403
    assert client.get(f"/api/repos/acme/shop/tests/{test_id}").json()["ai_enabled"] is False


def test_eval_results_endpoint(client, settings):
    assert client.get("/api/evals/latest").status_code == 404
    settings.evals_results_path.write_text('{"cases": []}')
    assert client.get("/api/evals/latest").json() == {"cases": []}
