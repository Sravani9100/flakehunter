"""Load the planted flaky-test cases in evals/cases/."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"


@dataclass(frozen=True)
class Case:
    name: str
    path: Path
    category: str
    accepted: tuple[str, ...]
    flaky_test: str
    root_cause: str
    expected_fix: str


def load_cases(names: list[str] | None = None) -> list[Case]:
    cases = []
    for case_dir in sorted(p for p in CASES_DIR.iterdir() if (p / "case.toml").is_file()):
        if names and case_dir.name not in names:
            continue
        meta = tomllib.loads((case_dir / "case.toml").read_text(encoding="utf-8"))
        cases.append(
            Case(
                name=case_dir.name,
                path=case_dir,
                category=meta["category"],
                accepted=(meta["category"], *meta.get("also_accept", [])),
                flaky_test=meta["flaky_test"],
                root_cause=meta["root_cause"],
                expected_fix=meta["expected_fix"],
            )
        )
    if names and len(cases) != len(names):
        missing = set(names) - {c.name for c in cases}
        raise SystemExit(f"Unknown case(s): {', '.join(sorted(missing))}")
    return cases
