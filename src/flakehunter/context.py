"""Assemble what the model sees about a flaky test: CI history, failures, and source."""

import ast
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from flakehunter.detection import ResultRow, compute_flake_stats
from flakehunter.models import Outcome, TestCase, TestResult, TestRun
from flakehunter.sandbox import RunStats
from flakehunter.testloc import TestLocation

MAX_FILE_CHARS = 30_000
MAX_FAILURE_CHARS = 4_000
MAX_FAILURES = 3
MAX_RELATED_FILES = 6


def build_context(
    session: Session,
    test_case: TestCase,
    workspace: Path,
    location: TestLocation,
    baseline: RunStats | None = None,
) -> str:
    rows = session.execute(
        select(TestResult, TestRun)
        .join(TestRun)
        .where(TestResult.test_case_id == test_case.id)
        .order_by(TestRun.created_at.desc())
    ).all()

    sections = [
        "# Flaky test\n\n"
        f"Identifier: `{test_case.identifier}`\n"
        f"pytest node ID: `{location.node_id}`\n"
        f"File: `{location.path}`"
    ]
    sections.append(_history(test_case.id, rows))
    if baseline is not None:
        sections.append(_baseline(baseline))
    sections.append(_failures(rows, baseline))
    sections.append(_sources(workspace, location))
    return "\n\n".join(s for s in sections if s)


def _history(test_case_id: int, rows) -> str:
    stats = compute_flake_stats(
        ResultRow(test_case_id, run.commit_sha, result.outcome, run.created_at)
        for result, run in rows
    ).get(test_case_id)
    if stats is None:
        return ""
    lines = [
        "## CI history",
        "",
        f"{stats.failures} failures in {stats.runs} runs ({stats.fail_rate:.0%}); "
        f"passed and failed on the same commit {stats.flaky_commits} time(s).",
    ]
    passed = [r.duration_s for r, _ in rows if r.outcome == Outcome.PASSED and r.duration_s]
    failed = [r.duration_s for r, _ in rows if r.outcome == Outcome.FAILED and r.duration_s]
    if passed and failed:
        lines.append(
            f"Average duration: {sum(passed) / len(passed):.3f}s when passing, "
            f"{sum(failed) / len(failed):.3f}s when failing."
        )
    return "\n".join(lines)


def _baseline(baseline: RunStats) -> str:
    text = (
        "## Local reproduction\n\n"
        f"Failed {baseline.failures} of {baseline.runs} fresh-process runs in the sandbox."
    )
    if baseline.failures == 0:
        text += (
            " It did not fail locally, so the flake may depend on CI conditions such as "
            "load, parallelism, or the environment."
        )
    return text


def _failures(rows, baseline: RunStats | None) -> str:
    outputs: list[str] = []
    seen: set[str] = set()
    for result, _ in rows:
        if result.outcome not in (Outcome.FAILED, Outcome.ERROR):
            continue
        key = result.message or result.details or ""
        if key in seen:
            continue
        seen.add(key)
        outputs.append("\n".join(p for p in (result.message, result.details) if p))
        if len(outputs) == MAX_FAILURES:
            break
    if not outputs and baseline is not None and baseline.last_failure:
        outputs.append(baseline.last_failure)
    if not outputs:
        return ""
    blocks = [f"```\n{o[-MAX_FAILURE_CHARS:]}\n```" for o in outputs]
    return "## Recent failure output\n\n" + "\n\n".join(blocks)


def _sources(workspace: Path, location: TestLocation) -> str:
    test_file = workspace / location.path
    files = [test_file, *related_files(workspace, test_file)]
    blocks = []
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        blocks.append(f"### `{path.relative_to(workspace).as_posix()}`\n\n```python\n{source}\n```")
    return "## Source\n\n" + "\n\n".join(blocks)


def related_files(workspace: Path, test_file: Path) -> list[Path]:
    """Local modules the test imports, plus conftest.py files that apply to it."""
    found: list[Path] = []

    def add(path: Path) -> None:
        if path.is_file() and path != test_file and path not in found:
            found.append(path)

    directory = test_file.parent
    while directory.is_relative_to(workspace):
        add(directory / "conftest.py")
        if directory == workspace:
            break
        directory = directory.parent

    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return found[:MAX_RELATED_FILES]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [(alias.name, 0) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules = [(base, node.level)]
            modules += [(f"{base}.{a.name}" if base else a.name, node.level) for a in node.names]
        else:
            continue
        for module, level in modules:
            for candidate in _module_paths(workspace, test_file, module, level):
                add(candidate)
    return found[:MAX_RELATED_FILES]


def _module_paths(workspace: Path, test_file: Path, module: str, level: int) -> list[Path]:
    if not module:
        return []
    relative = Path(*module.split("."))
    if level:
        bases = [test_file.parents[level - 1]]
    else:
        # Absolute imports may resolve from the root, a src/ layout, or the test's directory.
        bases = [workspace, workspace / "src", test_file.parent]
    paths = []
    for base in bases:
        paths += [base / relative.with_suffix(".py"), base / relative / "__init__.py"]
    return paths
