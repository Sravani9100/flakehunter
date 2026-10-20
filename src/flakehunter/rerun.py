"""Run one pytest node ID N times, each in a fresh interpreter, and print JSON results.

Standalone and stdlib-only so it can run inside a sandbox container.
Usage: python rerun.py <node_id> <runs> <workers> <timeout_s>
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

OUTPUT_LIMIT = 4000


def run_once(node_id: str, timeout: float) -> dict:
    # Fresh process per run, and no fixed hash seed, so per-process randomness shows up.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "pytest", node_id, "-q", "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": None, "output": f"timed out after {timeout}s"}
    output = (proc.stdout + proc.stderr)[-OUTPUT_LIMIT:]
    if proc.returncode == 5:
        output = "pytest collected no tests: the test was not found.\n" + output
    return {"passed": proc.returncode == 0, "exit_code": proc.returncode, "output": output}


def main() -> None:
    node_id, runs, workers, timeout = (
        sys.argv[1],
        int(sys.argv[2]),
        int(sys.argv[3]),
        float(sys.argv[4]),
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: run_once(node_id, timeout), range(runs)))
    print(json.dumps(results))


if __name__ == "__main__":
    main()
