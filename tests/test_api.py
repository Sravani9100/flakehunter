from tests.conftest import UPLOAD_TOKEN, junit

AUTH = {"Authorization": f"Bearer {UPLOAD_TOKEN}"}
RUNS_URL = "/api/repos/acme/shop/runs"


def upload(client, sha, *reports, headers=AUTH, **form):
    files = [("files", (f"report{i}.xml", r, "application/xml")) for i, r in enumerate(reports)]
    return client.post(RUNS_URL, data={"commit_sha": sha, **form}, files=files, headers=headers)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_requires_valid_token(client):
    report = junit({"test_a": "passed"})
    assert upload(client, "abc1234", report, headers={}).status_code == 401
    assert (
        upload(client, "abc1234", report, headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_upload_rejects_invalid_xml_and_sha(client):
    assert upload(client, "abc1234", "<oops").status_code == 422
    assert upload(client, "not-a-sha", junit({"test_a": "passed"})).status_code == 422


def test_upload_combines_multiple_reports_into_one_run(client):
    response = upload(client, "ABC1234", junit({"test_a": "passed"}), junit({"test_b": "failed"}))
    assert response.status_code == 201
    assert response.json()["results"] == 2
    assert response.json()["commit_sha"] == "abc1234"


def test_upload_is_idempotent_per_ci_run_attempt(client):
    report = junit({"test_a": "passed"})
    first = upload(client, "abc1234", report, ci_run_id="99", run_attempt="1").json()
    again = upload(client, "abc1234", report, ci_run_id="99", run_attempt="1").json()
    retry = upload(client, "abc1234", report, ci_run_id="99", run_attempt="2").json()
    assert first["id"] == again["id"]
    assert retry["id"] != first["id"]


def test_flaky_tests_end_to_end(client):
    upload(client, "aaa1111", junit({"test_checkout": "passed", "test_cart": "passed"}))
    upload(client, "aaa1111", junit({"test_checkout": "failed", "test_cart": "passed"}))
    # A consistent failure on a new commit is a regression, not a flake.
    upload(client, "bbb2222", junit({"test_checkout": "passed", "test_cart": "failed"}))

    response = client.get("/api/repos/acme/shop/flaky-tests")
    assert response.status_code == 200
    [flaky] = response.json()
    assert flaky["identifier"] == "tests.test_app::test_checkout"
    assert flaky["flaky_commits"] == 1
    assert flaky["runs"] == 3
    assert flaky["failures"] == 1

    history = client.get(f"/api/repos/acme/shop/tests/{flaky['id']}/results").json()
    assert [r["outcome"] for r in history] == ["passed", "failed", "passed"]
    assert history[1]["message"] == "assert 1 == 2"


def test_unknown_repo_and_test_return_404(client):
    assert client.get("/api/repos/nobody/nothing/flaky-tests").status_code == 404
    upload(client, "aaa1111", junit({"test_a": "passed"}))
    assert client.get("/api/repos/acme/shop/tests/999/results").status_code == 404
