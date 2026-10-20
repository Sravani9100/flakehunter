import pytest

from flakehunter.junit import JUnitParseError, parse_junit
from flakehunter.models import Outcome

PYTEST_REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4">
    <testcase classname="tests.test_cart" name="test_add" time="0.012" file="tests/test_cart.py"/>
    <testcase classname="tests.test_cart" name="test_total" time="0.5">
      <failure message="assert 9 == 10">tests/test_cart.py:14: AssertionError</failure>
    </testcase>
    <testcase classname="tests.test_cart" name="test_db" time="0.1">
      <error message="fixture 'db' failed">ConnectionRefusedError</error>
    </testcase>
    <testcase classname="tests.test_cart" name="test_slow">
      <skipped message="slow" />
    </testcase>
  </testsuite>
</testsuites>
"""

# Jest (jest-junit) nests suites and puts the describe block in classname.
JEST_REPORT = """<testsuites name="jest tests">
  <testsuite name="Cart">
    <testsuite name="nested">
      <testcase classname="Cart adds items" name="Cart adds items" time="0.003"/>
    </testsuite>
  </testsuite>
</testsuites>
"""


def test_parses_pytest_outcomes():
    cases = {c.identifier: c for c in parse_junit(PYTEST_REPORT)}

    assert cases["tests.test_cart::test_add"].outcome == Outcome.PASSED
    assert cases["tests.test_cart::test_add"].file == "tests/test_cart.py"
    assert cases["tests.test_cart::test_add"].duration_s == pytest.approx(0.012)

    failed = cases["tests.test_cart::test_total"]
    assert failed.outcome == Outcome.FAILED
    assert failed.message == "assert 9 == 10"
    assert "AssertionError" in failed.details

    assert cases["tests.test_cart::test_db"].outcome == Outcome.ERROR
    assert cases["tests.test_cart::test_slow"].outcome == Outcome.SKIPPED
    assert cases["tests.test_cart::test_slow"].duration_s is None


def test_finds_cases_in_nested_suites():
    [case] = parse_junit(JEST_REPORT)
    assert case.identifier == "Cart adds items::Cart adds items"


def test_single_testsuite_root_is_accepted():
    [case] = parse_junit('<testsuite><testcase name="test_x"/></testsuite>')
    assert case.identifier == "test_x"


@pytest.mark.parametrize("xml", ["not xml", "<html><body/></html>"])
def test_rejects_non_junit(xml):
    with pytest.raises(JUnitParseError):
        parse_junit(xml)


def test_rejects_entity_expansion():
    billion_laughs = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<testsuites><testcase name="&lol2;"/></testsuites>"""
    with pytest.raises(JUnitParseError):
        parse_junit(billion_laughs)
