from pathlib import PurePosixPath

import pytest

from flakehunter.testloc import TestNotFoundError, locate_test
from tests.fakes import make_repo


@pytest.fixture
def repo(tmp_path):
    root = make_repo(tmp_path / "repo")
    (root / "tests" / "test_classes.py").write_text("class TestCart:\n    def test_x(self): pass\n")
    return root


def test_module_path(repo):
    loc = locate_test(repo, "tests.test_clock::test_ready")
    assert loc.path == PurePosixPath("tests/test_clock.py")
    assert loc.node_id == "tests/test_clock.py::test_ready"
    assert loc.class_name is None


def test_class_and_parametrize(repo):
    loc = locate_test(repo, "tests.test_classes.TestCart::test_x[2-3]")
    assert loc.node_id == "tests/test_classes.py::TestCart::test_x[2-3]"
    assert loc.function == "test_x"
    assert loc.class_name == "TestCart"


def test_drops_leading_segments_from_a_different_rootdir(repo):
    loc = locate_test(repo, "backend.tests.test_clock::test_ready")
    assert loc.node_id == "tests/test_clock.py::test_ready"


def test_file_hint_wins(repo):
    loc = locate_test(repo, "whatever::test_ready", file_hint="tests/test_clock.py")
    assert loc.path == PurePosixPath("tests/test_clock.py")


def test_missing(repo):
    with pytest.raises(TestNotFoundError):
        locate_test(repo, "tests.test_nope::test_ready")
