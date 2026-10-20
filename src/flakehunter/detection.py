"""Flake detection.

A test is flaky when it both passed and failed on the same commit. Same code with a
different outcome means something nondeterministic is involved: timing, test order,
randomness, or the environment. A real regression does not trigger this rule, because a
test broken by a commit fails consistently on that commit.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from flakehunter.models import Outcome

_FAILING = {Outcome.FAILED, Outcome.ERROR}


@dataclass(frozen=True)
class ResultRow:
    test_case_id: int
    commit_sha: str
    outcome: Outcome
    recorded_at: datetime


@dataclass
class FlakeStats:
    test_case_id: int
    runs: int = 0
    failures: int = 0
    flaky_commits: int = 0
    last_flake_at: datetime | None = None

    @property
    def fail_rate(self) -> float:
        return self.failures / self.runs if self.runs else 0.0

    @property
    def is_flaky(self) -> bool:
        return self.flaky_commits > 0


@dataclass
class _CommitOutcomes:
    passed: bool = False
    latest_failure: datetime | None = None


def compute_flake_stats(rows: Iterable[ResultRow]) -> dict[int, FlakeStats]:
    stats: dict[int, FlakeStats] = {}
    commits: defaultdict[tuple[int, str], _CommitOutcomes] = defaultdict(_CommitOutcomes)

    for row in rows:
        if row.outcome == Outcome.SKIPPED:
            continue
        test = stats.setdefault(row.test_case_id, FlakeStats(row.test_case_id))
        commit = commits[(row.test_case_id, row.commit_sha)]
        test.runs += 1
        if row.outcome in _FAILING:
            test.failures += 1
            if commit.latest_failure is None or row.recorded_at > commit.latest_failure:
                commit.latest_failure = row.recorded_at
        else:
            commit.passed = True

    for (test_case_id, _), commit in commits.items():
        if commit.passed and commit.latest_failure is not None:
            test = stats[test_case_id]
            test.flaky_commits += 1
            # The last flake is the last failure on a commit that also passed.
            if test.last_flake_at is None or commit.latest_failure > test.last_flake_at:
                test.last_flake_at = commit.latest_failure

    return stats


def rank_flaky(stats: dict[int, FlakeStats]) -> list[FlakeStats]:
    """Flaky tests only, most disruptive first."""
    return sorted(
        (s for s in stats.values() if s.is_flaky),
        key=lambda s: (s.flaky_commits, s.fail_rate),
        reverse=True,
    )
