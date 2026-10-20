"""Reject "fixes" that make a test pass by no longer testing anything.

Verification proves the test stops failing; these checks make sure it still tests.
Blocking issues reject the fix. Review notes are shown to a human but don't block.
"""

import ast
import re
from dataclasses import dataclass, field

from flakehunter.testloc import TestLocation

_SUPPRESSORS = re.compile(
    r"pytest\.mark\.(skip|skipif|xfail|flaky)|pytest\.(skip|xfail)\(|@flaky|reruns\s*=", re.I
)


@dataclass
class IntegrityReport:
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_integrity(
    original: dict[str, str], updated: dict[str, str], location: TestLocation
) -> IntegrityReport:
    report = IntegrityReport()

    for path, new_source in updated.items():
        old_lines = set(original.get(path, "").splitlines())
        added = [line for line in new_source.splitlines() if line not in old_lines]
        if any(_SUPPRESSORS.search(line) for line in added):
            report.issues.append(f"{path}: adds a skip, xfail, or rerun marker.")

    test_path = str(location.path)
    if test_path in updated:
        old_fn = _find_test(original.get(test_path, ""), location)
        new_fn = _find_test(updated[test_path], location)
        if new_fn is None:
            report.issues.append("The flaky test was removed or renamed.")
        elif _count_checks(new_fn) == 0:
            report.issues.append("The test no longer checks anything.")
        elif old_fn is not None and _count_checks(new_fn) < _count_checks(old_fn):
            report.notes.append(
                "The test has fewer assertions than before. Confirm the removed check "
                "wasn't a real requirement."
            )
    return report


def _find_test(source: str, location: TestLocation) -> ast.AST | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    scope: list[ast.stmt] = tree.body
    if location.class_name:
        cls = next(
            (n for n in scope if isinstance(n, ast.ClassDef) and n.name == location.class_name),
            None,
        )
        if cls is None:
            return None
        scope = cls.body
    return next(
        (
            n
            for n in scope
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == location.function
        ),
        None,
    )


def _count_checks(fn: ast.AST) -> int:
    """Count assert statements, unittest assert* calls, and pytest.raises blocks."""
    count = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith("assert") or name in ("raises", "warns"):
                count += 1
    return count
