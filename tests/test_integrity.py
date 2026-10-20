from pathlib import PurePosixPath

from flakehunter.integrity import check_integrity
from flakehunter.testloc import TestLocation

LOC = TestLocation(
    path=PurePosixPath("tests/test_x.py"),
    node_id="tests/test_x.py::test_x",
    function="test_x",
    class_name=None,
)
ORIGINAL = {"tests/test_x.py": "def test_x():\n    assert a()\n    assert b()\n"}


def check(new_source, path="tests/test_x.py"):
    return check_integrity(ORIGINAL, {path: new_source}, LOC)


def test_real_fix_passes():
    report = check("def test_x():\n    wait()\n    assert a()\n    assert b()\n")
    assert report.issues == [] and report.notes == []


def test_skip_marker_is_rejected():
    report = check("import pytest\n@pytest.mark.skip\ndef test_x():\n    assert a()\n")
    assert any("skip" in issue for issue in report.issues)


def test_rerun_marker_in_another_file_is_rejected():
    report = check_integrity({}, {"conftest.py": "pytestmark = pytest.mark.flaky(reruns=3)\n"}, LOC)
    assert report.issues


def test_deleted_test_is_rejected():
    assert check("def test_other():\n    assert a()\n").issues


def test_gutted_test_is_rejected():
    assert check("def test_x():\n    a()\n").issues


def test_fewer_asserts_is_a_note_not_a_rejection():
    report = check("def test_x():\n    assert a()\n")
    assert report.issues == []
    assert report.notes


def test_unittest_style_asserts_count():
    original = {
        "tests/test_x.py": "class T:\n    def test_x(self):\n        self.assertEqual(1, 1)\n"
    }
    loc = TestLocation(LOC.path, "tests/test_x.py::T::test_x", "test_x", "T")
    updated = {"tests/test_x.py": "class T:\n    def test_x(self):\n        self.assertTrue(f())\n"}
    assert check_integrity(original, updated, loc).issues == []
