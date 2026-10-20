"""Database models.

A TestRun is one CI execution: one workflow run attempt, or one upload. It holds a
TestResult per test case. Flakiness is derived from results at query time, not stored.
"""

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flakehunter.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def _str_enum(cls: type[enum.StrEnum]) -> Enum:
    # Store values ("passed"), not names ("PASSED"), as plain strings.
    return Enum(cls, native_enum=False, length=10, values_callable=lambda e: [m.value for m in e])


class Outcome(enum.StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    installation_id: Mapped[int | None] = mapped_column(BigInteger)
    # Dev and evals only: a local checkout used instead of cloning from GitHub.
    local_path: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (UniqueConstraint("repo_id", "ci_run_id", "run_attempt"),)
    __test__ = False  # not a pytest test class

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    branch: Mapped[str | None] = mapped_column(String(255))
    ci_run_id: Mapped[int | None] = mapped_column(BigInteger)
    run_attempt: Mapped[int] = mapped_column(default=1)
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    results: Mapped[list["TestResult"]] = relationship(back_populates="run")


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("repo_id", "identifier"),)
    __test__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    # "classname::name" from the JUnit report, e.g. "tests.test_api::test_upload".
    identifier: Mapped[str] = mapped_column(String(1000))
    file: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestResult(Base):
    __tablename__ = "test_results"
    __test__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), index=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    outcome: Mapped[Outcome] = mapped_column(_str_enum(Outcome))
    duration_s: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    # Failure output (stack trace). This is the main input for AI diagnosis later.
    details: Mapped[str | None] = mapped_column(Text)

    run: Mapped[TestRun] = relationship(back_populates="results")
    test_case: Mapped[TestCase] = relationship()


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_fix: Mapped[str] = mapped_column(Text)
    thinking: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(50))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FixStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    VERIFIED = "verified"  # passed every verification run and the integrity checks
    NOT_FIXED = "not_fixed"  # no change, or still failed during verification
    REJECTED = "rejected"  # "fixed" the test by skipping, deleting, or gutting it
    ERROR = "error"


class FixAttempt(Base):
    __tablename__ = "fix_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[FixStatus] = mapped_column(_str_enum(FixStatus), default=FixStatus.QUEUED)
    category: Mapped[str | None] = mapped_column(String(30))
    explanation: Mapped[str | None] = mapped_column(Text)
    diff: Mapped[str | None] = mapped_column(Text)
    # Full new contents of each changed file, used to open the pull request.
    files: Mapped[dict[str, str] | None] = mapped_column(JSON)
    integrity_issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    review_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    baseline_runs: Mapped[int | None] = mapped_column(Integer)
    baseline_failures: Mapped[int | None] = mapped_column(Integer)
    verification_runs: Mapped[int | None] = mapped_column(Integer)
    verification_failures: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_s: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    pr_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    test_case: Mapped[TestCase] = relationship()
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="fix_attempt", order_by="AgentStep.index"
    )


class AgentStep(Base):
    """One entry in the fix agent's trace: a thought, a message, or a tool call."""

    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    fix_attempt_id: Mapped[int] = mapped_column(ForeignKey("fix_attempts.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # "thinking" | "text" | "tool"
    tool: Mapped[str | None] = mapped_column(String(50))
    input: Mapped[dict | None] = mapped_column(JSON)
    output: Mapped[str | None] = mapped_column(Text)
    is_error: Mapped[bool] = mapped_column(default=False)
    duration_s: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fix_attempt: Mapped[FixAttempt] = relationship(back_populates="steps")
