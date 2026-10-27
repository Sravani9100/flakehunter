"""Score diagnosis and the fix agent against every planted flaky test.

Runs the production code path (context building, diagnosis, fix agent, sandbox
verification, integrity checks) against a throwaway database. Each case is scored on:

- diagnosis: is the root-cause category one the case accepts?
- fix: did the patched test pass every verification run without gaming the checks?

Needs Anthropic credentials and spends real money. Results go to evals/results/.

Usage: python evals/run_evals.py [case ...] [--verify-runs 100]
"""

import argparse
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))

from case_loader import Case, load_cases  # noqa: E402

from flakehunter.config import get_settings  # noqa: E402
from flakehunter.context import build_context  # noqa: E402
from flakehunter.db import Base, make_engine  # noqa: E402
from flakehunter.diagnosis import run_diagnosis  # noqa: E402
from flakehunter.fixes import run_fix_attempt  # noqa: E402
from flakehunter.llm import make_client  # noqa: E402
from flakehunter.models import Diagnosis, FixAttempt, Repository, TestCase  # noqa: E402
from flakehunter.sandbox import make_sandbox  # noqa: E402
from flakehunter.testloc import locate_test  # noqa: E402
from flakehunter.workspace import checkout  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
NO_COMMIT = "0" * 40


def run_case(case: Case, client, base_settings) -> dict:
    started = time.monotonic()
    # Windows can hold the SQLite file open briefly after dispose(); don't fail on cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = base_settings.model_copy(
            update={"database_url": f"sqlite:///{tmp}/evals.db", "allow_local_repos": True}
        )
        engine = make_engine(settings.database_url)
        Base.metadata.create_all(engine)
        make_session = sessionmaker(engine, expire_on_commit=False)
        sandbox = make_sandbox(settings)

        with make_session() as session:
            repo = Repository(full_name=f"evals/{case.name}", local_path=str(case.path))
            session.add(repo)
            session.flush()
            test_case = TestCase(repo_id=repo.id, identifier=case.flaky_test)
            session.add(test_case)
            session.flush()

            with checkout(repo, NO_COMMIT, None, settings) as workspace:
                location = locate_test(workspace, case.flaky_test)
                baseline = sandbox.run_test(workspace, location.node_id, settings.baseline_runs)
                context = build_context(session, test_case, workspace, location, baseline)
            diagnosis: Diagnosis = list(run_diagnosis(client, settings, test_case.id, context))[-1]
            session.add(diagnosis)
            attempt = FixAttempt(test_case_id=test_case.id, commit_sha=NO_COMMIT)
            session.add(attempt)
            session.commit()
            attempt_id = attempt.id

        run_fix_attempt(
            make_session, attempt_id, client=client, settings=settings, sandbox=sandbox, github=None
        )

        with make_session() as session:
            attempt = session.get(FixAttempt, attempt_id)
            row = {
                "case": case.name,
                "expected_category": case.category,
                "accepted_categories": list(case.accepted),
                "diagnosis_category": diagnosis.category,
                "diagnosis_correct": diagnosis.category in case.accepted,
                "diagnosis_summary": diagnosis.summary,
                "fix_status": attempt.status.value,
                "fix_category": attempt.category,
                "baseline": [attempt.baseline_failures, attempt.baseline_runs],
                "verification": [attempt.verification_failures, attempt.verification_runs],
                "integrity_issues": attempt.integrity_issues or [],
                "review_notes": attempt.review_notes or [],
                "agent_steps": len(attempt.steps),
                "explanation": attempt.explanation,
                "diff": attempt.diff,
                "error": attempt.error,
                "cost_usd": round(diagnosis.cost_usd + attempt.cost_usd, 4),
                "duration_s": round(time.monotonic() - started, 1),
            }
        engine.dispose()  # release the SQLite file so the temp dir can be removed
        return row


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    return {
        "cases": total,
        "verified_fixes": sum(r["fix_status"] == "verified" for r in rows),
        "rejected_fixes": sum(r["fix_status"] == "rejected" for r in rows),
        "diagnosis_correct": sum(r["diagnosis_correct"] for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 3),
        "mean_cost_usd": round(sum(r["cost_usd"] for r in rows) / total, 3) if total else 0,
        "mean_duration_s": round(sum(r["duration_s"] for r in rows) / total, 1) if total else 0,
    }


def print_table(rows: list[dict], summary: dict) -> None:
    print("\n| Case | Diagnosis | Fix | Verification | Cost | Time |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        mark = "ok" if r["diagnosis_correct"] else "WRONG"
        failures, runs = r["verification"]
        verification = f"{runs - failures}/{runs} passed" if runs else "-"
        print(
            f"| {r['case']} | {r['diagnosis_category']} ({mark}) | {r['fix_status']} | "
            f"{verification} | ${r['cost_usd']:.3f} | {r['duration_s']:.0f}s |"
        )
    print(
        f"\nVerified fixes: {summary['verified_fixes']}/{summary['cases']}  |  "
        f"Diagnosis accuracy: {summary['diagnosis_correct']}/{summary['cases']}  |  "
        f"Total cost: ${summary['total_cost_usd']:.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="*", help="case names (default: all)")
    parser.add_argument("--verify-runs", type=int)
    args = parser.parse_args()

    settings = get_settings()
    if args.verify_runs:
        settings = settings.model_copy(update={"verify_runs": args.verify_runs})
    client = make_client(settings)

    rows = []
    for case in load_cases(args.cases or None):
        print(f"Running {case.name}...", flush=True)
        try:
            rows.append(run_case(case, client, settings))
        except Exception as exc:  # one broken case shouldn't lose the others' results
            print(f"  {case.name} crashed: {exc}", flush=True)
            rows.append({"case": case.name, "fix_status": "error", "diagnosis_correct": False,
                         "diagnosis_category": None, "verification": [None, None],
                         "error": str(exc), "cost_usd": 0.0, "duration_s": 0.0})  # fmt: skip

    summary = summarize(rows)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": settings.anthropic_model,
        "effort": settings.ai_effort,
        "verify_runs": settings.verify_runs,
        "summary": summary,
        "results": rows,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    for path in (RESULTS_DIR / "latest.json", RESULTS_DIR / f"run-{stamp}.json"):
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_table(rows, summary)


if __name__ == "__main__":
    main()
