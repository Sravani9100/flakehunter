"""Run a test many times in fresh processes to measure its flake rate."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from flakehunter.config import Settings

RERUN_SCRIPT = Path(__file__).with_name("rerun.py")


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunStats:
    runs: int
    failures: int
    last_failure: str | None = None


class Sandbox(Protocol):
    def run_test(self, workspace: Path, node_id: str, runs: int) -> RunStats: ...


class SubprocessSandbox:
    """Local processes with FlakeHunter's own interpreter.

    Isolation is process-level only: use it for trusted code (your repositories, the
    eval cases). Use DockerSandbox for anything else.
    """

    def __init__(self, workers: int = 8, timeout_s: float = 60) -> None:
        self.workers = workers
        self.timeout_s = timeout_s

    def run_test(self, workspace: Path, node_id: str, runs: int) -> RunStats:
        command = [
            sys.executable,
            str(RERUN_SCRIPT),
            node_id,
            str(runs),
            str(self.workers),
            str(self.timeout_s),
        ]
        return _execute(command, cwd=workspace, timeout=self.timeout_s * runs + 60)


class DockerSandbox:
    """One container per batch: no network, capped CPU and memory.

    The image must contain pytest and the project's dependencies.
    """

    def __init__(self, image: str, workers: int = 4, timeout_s: float = 60) -> None:
        self.image = image
        self.workers = workers
        self.timeout_s = timeout_s

    def run_test(self, workspace: Path, node_id: str, runs: int) -> RunStats:
        command = [
            "docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "2g",
            "-v", f"{workspace.resolve()}:/work", "-v", f"{RERUN_SCRIPT}:/opt/rerun.py:ro",
            "-w", "/work", self.image,
            "python", "/opt/rerun.py", node_id, str(runs), str(self.workers), str(self.timeout_s),
        ]  # fmt: skip
        return _execute(command, cwd=workspace, timeout=self.timeout_s * runs + 120)


def make_sandbox(settings: Settings) -> Sandbox:
    if settings.sandbox == "docker":
        return DockerSandbox(settings.sandbox_image, workers=settings.sandbox_workers)
    return SubprocessSandbox(workers=settings.sandbox_workers)


def _execute(command: list[str], *, cwd: Path, timeout: float) -> RunStats:
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SandboxError("test reruns timed out") from exc
    if proc.returncode != 0:
        raise SandboxError(f"rerun failed: {proc.stderr[-2000:]}")
    results = json.loads(proc.stdout)
    failures = [r for r in results if not r["passed"]]
    return RunStats(
        runs=len(results),
        failures=len(failures),
        last_failure=failures[-1]["output"] if failures else None,
    )
