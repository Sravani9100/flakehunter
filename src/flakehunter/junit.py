"""JUnit XML parsing.

Reports come from untrusted CI jobs, so parsing goes through defusedxml to reject
entity-expansion and external-entity attacks.
"""

from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException, ElementTree

from flakehunter.models import Outcome

_MAX_TEXT = 20_000
_OUTCOME_TAGS = {
    "failure": Outcome.FAILED,
    "error": Outcome.ERROR,
    "skipped": Outcome.SKIPPED,
}


class JUnitParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCase:
    identifier: str
    outcome: Outcome
    duration_s: float | None = None
    message: str | None = None
    details: str | None = None
    file: str | None = None


def parse_junit(xml: bytes | str) -> list[ParsedCase]:
    try:
        root = ElementTree.fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise JUnitParseError(f"invalid JUnit XML: {exc}") from exc
    if root.tag not in ("testsuites", "testsuite"):
        raise JUnitParseError(f"unexpected root element <{root.tag}>")
    # iter() also finds test cases inside nested <testsuite> elements (Jest, Gradle).
    return [_parse_case(el) for el in root.iter("testcase") if el.get("name")]


def _parse_case(el: Element) -> ParsedCase:
    name = el.get("name", "")
    classname = el.get("classname")
    outcome, message, details = Outcome.PASSED, None, None
    for child in el:
        if child.tag in _OUTCOME_TAGS:
            outcome = _OUTCOME_TAGS[child.tag]
            message = _truncate(child.get("message"))
            details = _truncate(child.text)
            break
    return ParsedCase(
        identifier=f"{classname}::{name}" if classname else name,
        outcome=outcome,
        duration_s=_parse_float(el.get("time")),
        message=message,
        details=details,
        file=el.get("file"),
    )


def _truncate(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    return text.strip()[:_MAX_TEXT]


def _parse_float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
