"""Throwaway source checkouts for diagnosis and fix jobs."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from flakehunter.config import Settings
from flakehunter.github import GitHubClient
from flakehunter.models import Repository

_IGNORE = shutil.ignore_patterns(".git", ".venv", "node_modules", "__pycache__", ".pytest_cache")


class WorkspaceError(RuntimeError):
    pass


@contextmanager
def checkout(
    repo: Repository, commit_sha: str, github: GitHubClient | None, settings: Settings
) -> Iterator[Path]:
    tmp = Path(tempfile.mkdtemp(prefix="flakehunter-"))
    dest = tmp / "repo"
    try:
        if repo.local_path:
            if not settings.allow_local_repos:
                raise WorkspaceError("Local repositories are disabled")
            shutil.copytree(repo.local_path, dest, ignore=_IGNORE)
        elif github is not None and repo.installation_id is not None:
            github.clone(repo.installation_id, repo.full_name, commit_sha, dest)
        else:
            raise WorkspaceError("No source available: install the GitHub App on this repository")
        yield dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
