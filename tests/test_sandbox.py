"""Runs real pytest subprocesses, so these take a few seconds."""

from flakehunter.sandbox import SubprocessSandbox
from tests.fakes import make_repo


def test_counts_failures_across_fresh_processes(tmp_path):
    repo = make_repo(tmp_path / "repo")
    (repo / "tests" / "test_fixed.py").write_text(
        "def test_pass():\n    assert True\n\n\ndef test_fail():\n    assert 1 == 2\n"
    )
    sandbox = SubprocessSandbox(workers=3, timeout_s=60)

    passing = sandbox.run_test(repo, "tests/test_fixed.py::test_pass", runs=3)
    assert (passing.runs, passing.failures, passing.last_failure) == (3, 0, None)

    failing = sandbox.run_test(repo, "tests/test_fixed.py::test_fail", runs=3)
    assert failing.failures == 3
    assert "assert 1 == 2" in failing.last_failure


def test_missing_test_counts_as_failure(tmp_path):
    repo = make_repo(tmp_path / "repo")
    stats = SubprocessSandbox(workers=1).run_test(repo, "tests/test_clock.py::test_gone", runs=1)
    assert stats.failures == 1
