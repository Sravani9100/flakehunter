from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from flakehunter.models import FixStatus, Outcome

# SQLite drops timezone info; everything is stored in UTC, so restore it on the way out.
UTCDatetime = Annotated[
    datetime, AfterValidator(lambda d: d if d.tzinfo else d.replace(tzinfo=UTC))
]


class RunOut(BaseModel):
    id: int
    commit_sha: str
    run_attempt: int
    results: int


class RepoOut(BaseModel):
    full_name: str
    source: str  # "github" | "local" | "upload"
    flaky_tests: int
    total_runs: int
    last_run_at: UTCDatetime | None


class RepoCreate(BaseModel):
    full_name: str = Field(pattern=r"^[\w.-]+/[\w.-]+$")
    local_path: str


class FlakyTestOut(BaseModel):
    id: int
    identifier: str
    file: str | None
    runs: int
    failures: int
    fail_rate: float
    flaky_commits: int
    last_flake_at: UTCDatetime | None


class ResultOut(BaseModel):
    run_id: int
    commit_sha: str
    branch: str | None
    run_attempt: int
    outcome: Outcome
    duration_s: float | None
    message: str | None
    details: str | None = None
    recorded_at: UTCDatetime


class StatsOut(BaseModel):
    runs: int
    failures: int
    fail_rate: float
    flaky_commits: int
    last_flake_at: UTCDatetime | None


class DiagnosisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    confidence: float
    summary: str
    explanation: str
    evidence: list[str]
    suggested_fix: str
    thinking: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_s: float
    created_at: UTCDatetime


class FixAttemptSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: FixStatus
    commit_sha: str
    category: str | None
    baseline_runs: int | None
    baseline_failures: int | None
    verification_runs: int | None
    verification_failures: int | None
    cost_usd: float
    duration_s: float | None
    pr_url: str | None
    created_at: UTCDatetime
    finished_at: UTCDatetime | None


class AgentStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    kind: str
    tool: str | None
    input: dict | None
    output: str | None
    is_error: bool
    duration_s: float | None


class FixAttemptOut(FixAttemptSummary):
    test_case_id: int
    repo: str
    test_identifier: str
    explanation: str | None
    diff: str | None
    integrity_issues: list[str]
    review_notes: list[str]
    model: str | None
    input_tokens: int
    output_tokens: int
    error: str | None
    can_open_pr: bool
    steps: list[AgentStepOut]


class TestDetailOut(BaseModel):
    __test__ = False

    id: int
    repo: str
    identifier: str
    file: str | None
    stats: StatsOut | None
    latest_failure: ResultOut | None
    history: list[ResultOut]
    diagnosis: DiagnosisOut | None
    fix_attempts: list[FixAttemptSummary]
    ai_enabled: bool
