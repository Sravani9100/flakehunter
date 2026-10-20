"""Measure each eval case's flake rate using the same sandbox the fix agent uses.

Runs are fresh processes in parallel, like CI with pytest-xdist, so flakes that only
appear under parallelism show up too. No API key needed.

Usage: python evals/measure_flake_rate.py [case ...] [-n 30]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from case_loader import load_cases  # noqa: E402

from flakehunter.sandbox import SubprocessSandbox  # noqa: E402
from flakehunter.testloc import locate_test  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="*", help="case names (default: all)")
    parser.add_argument("-n", "--runs", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    sandbox = SubprocessSandbox(workers=args.workers)
    for case in load_cases(args.cases or None):
        location = locate_test(case.path, case.flaky_test)
        stats = sandbox.run_test(case.path, location.node_id, args.runs)
        rate = stats.failures / stats.runs
        print(f"{rate:6.0%}  {stats.failures:>3}/{stats.runs:<3}  {case.name:<16} {case.category}")
        # Parallel runs can leave files behind (shared_file writes report.json).
        (case.path / "report.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
