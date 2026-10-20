import pytest
from fastapi.testclient import TestClient

from flakehunter.config import Settings
from flakehunter.main import create_app
from tests.fakes import FakeClient, FakeSandbox

UPLOAD_TOKEN = "test-token"
WEBHOOK_SECRET = "webhook-secret"


def junit(outcomes: dict[str, str], classname: str = "tests.test_app") -> str:
    """Build a pytest-style JUnit report from {test_name: "passed" | "failed" | ...}."""
    children = {
        "passed": "",
        "failed": '<failure message="assert 1 == 2">Traceback...</failure>',
        "error": '<error message="fixture error">Traceback...</error>',
        "skipped": '<skipped message="skip" />',
    }
    cases = "".join(
        f'<testcase classname="{classname}" name="{name}" time="0.01">{children[outcome]}'
        "</testcase>"
        for name, outcome in outcomes.items()
    )
    return f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>'


class FakeGitHub:
    """Returns queued reports, one list per fetch_junit_reports call."""

    def __init__(self) -> None:
        self.queued: list[list[bytes]] = []
        self.calls: list[dict] = []
        self.pull_requests: list[dict] = []

    def fetch_junit_reports(self, **kwargs) -> list[bytes]:
        self.calls.append(kwargs)
        return self.queued.pop(0) if self.queued else []

    def open_pull_request(self, **kwargs) -> str:
        self.pull_requests.append(kwargs)
        return "https://github.com/acme/shop/pull/7"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_token=UPLOAD_TOKEN,
        github_webhook_secret=WEBHOOK_SECRET,
        allow_local_repos=True,
        evals_results_path=tmp_path / "evals.json",
    )


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def fake_llm() -> FakeClient:
    return FakeClient()


@pytest.fixture
def fake_sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
def client(settings, fake_github, fake_llm, fake_sandbox):
    app = create_app(settings, github_client=fake_github, llm_client=fake_llm, sandbox=fake_sandbox)
    with TestClient(app) as test_client:
        yield test_client
