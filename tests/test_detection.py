from datetime import UTC, datetime, timedelta

from flakehunter.detection import ResultRow, compute_flake_stats, rank_flaky
from flakehunter.models import Outcome

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def row(test_id, sha, outcome, minutes=0):
    return ResultRow(test_id, sha, Outcome(outcome), T0 + timedelta(minutes=minutes))


def test_pass_and_fail_on_same_commit_is_flaky():
    stats = compute_flake_stats(
        [row(1, "aaa", "passed", 0), row(1, "aaa", "failed", 5), row(1, "bbb", "passed", 10)]
    )
    assert stats[1].is_flaky
    assert stats[1].flaky_commits == 1
    assert stats[1].runs == 3
    assert stats[1].failures == 1
    assert stats[1].last_flake_at == T0 + timedelta(minutes=5)


def test_last_flake_is_the_last_failure_not_the_last_run():
    stats = compute_flake_stats(
        [row(1, "aaa", "failed", 0), row(1, "aaa", "passed", 30), row(1, "aaa", "passed", 60)]
    )
    assert stats[1].last_flake_at == T0


def test_regression_then_fix_is_not_flaky():
    # Broken on bbb and fixed on ccc: every commit has a consistent outcome.
    stats = compute_flake_stats(
        [
            row(1, "aaa", "passed"),
            row(1, "bbb", "failed"),
            row(1, "bbb", "failed"),
            row(1, "ccc", "passed"),
        ]
    )
    assert not stats[1].is_flaky


def test_error_counts_as_failure_and_skipped_is_ignored():
    stats = compute_flake_stats(
        [
            row(1, "aaa", "error"),
            row(1, "aaa", "passed"),
            row(2, "aaa", "skipped"),
            row(2, "aaa", "passed"),
        ]
    )
    assert stats[1].is_flaky
    assert stats[2].runs == 1
    assert not stats[2].is_flaky


def test_rank_orders_by_flaky_commits_then_fail_rate():
    rows = [
        # test 1: flaky on one commit, 50% fail rate
        row(1, "a", "passed"),
        row(1, "a", "failed"),
        # test 2: flaky on two commits, 50% fail rate
        row(2, "a", "passed"),
        row(2, "a", "failed"),
        row(2, "b", "passed"),
        row(2, "b", "failed"),
        # test 3: flaky on one commit, 67% fail rate
        row(3, "a", "passed"),
        row(3, "a", "failed"),
        row(3, "a", "failed"),
        # test 4: never flaky
        row(4, "a", "passed"),
    ]
    assert [s.test_case_id for s in rank_flaky(compute_flake_stats(rows))] == [2, 3, 1]
