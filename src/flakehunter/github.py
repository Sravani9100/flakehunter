"""GitHub App integration: webhook verification and JUnit artifact download."""

import base64
import hashlib
import hmac
import io
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Self
from urllib.parse import quote

import httpx
import jwt

from flakehunter.config import Settings

MAX_ARTIFACT_BYTES = 50 * 1024 * 1024


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Check GitHub's X-Hub-Signature-256 header against the raw request body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def extract_xml_files(archive: bytes) -> list[bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir() and m.filename.endswith(".xml")]
        if sum(m.file_size for m in members) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds size limit")
        return [zf.read(m) for m in members]


class GitHubClient:
    def __init__(
        self,
        app_id: str,
        private_key: str,
        api_url: str = "https://api.github.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        # httpx drops the Authorization header when an artifact download redirects to
        # blob storage on another host, which is required for the download to succeed.
        self._http = httpx.Client(
            base_url=api_url,
            transport=transport,
            follow_redirects=True,
            timeout=30,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> Self | None:
        if not (settings.github_app_id and settings.github_private_key_path):
            return None
        private_key = settings.github_private_key_path.read_text()
        return cls(settings.github_app_id, private_key, settings.github_api_url)

    def fetch_junit_reports(
        self, *, installation_id: int, repo_full_name: str, run_id: int, name_pattern: str
    ) -> list[bytes]:
        auth = {"Authorization": f"Bearer {self._installation_token(installation_id)}"}
        response = self._http.get(
            f"/repos/{repo_full_name}/actions/runs/{run_id}/artifacts",
            params={"per_page": 100},
            headers=auth,
        )
        response.raise_for_status()

        pattern = re.compile(name_pattern, re.IGNORECASE)
        reports: list[bytes] = []
        for artifact in response.json()["artifacts"]:
            if artifact.get("expired") or not pattern.search(artifact["name"]):
                continue
            archive = self._http.get(artifact["archive_download_url"], headers=auth)
            archive.raise_for_status()
            reports.extend(extract_xml_files(archive.content))
        return reports

    def clone(self, installation_id: int, repo_full_name: str, commit_sha: str, dest: Path) -> None:
        """Shallow-fetch a single commit into dest."""
        token = self._installation_token(installation_id)
        url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
        dest.mkdir(parents=True)
        for args in (
            ["init", "-q"],
            ["fetch", "-q", "--depth", "1", url, commit_sha],
            ["checkout", "-q", "FETCH_HEAD"],
        ):
            proc = subprocess.run(["git", *args], cwd=dest, capture_output=True, text=True)
            if proc.returncode != 0:
                # Never echo the command: the URL contains the token.
                raise RuntimeError(f"git {args[0]} failed: {proc.stderr.replace(token, '***')}")

    def open_pull_request(
        self,
        *,
        installation_id: int,
        repo_full_name: str,
        base_sha: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        """Commit files onto a new branch from base_sha and open a PR. Returns its URL."""
        auth = {"Authorization": f"Bearer {self._installation_token(installation_id)}"}
        repo_path = f"/repos/{repo_full_name}"

        repo = self._http.get(repo_path, headers=auth)
        repo.raise_for_status()
        ref = self._http.post(
            f"{repo_path}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            headers=auth,
        )
        ref.raise_for_status()

        for path, content in files.items():
            url = f"{repo_path}/contents/{quote(path)}"
            existing = self._http.get(url, params={"ref": branch}, headers=auth)
            payload = {
                "message": title,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch,
            }
            if existing.status_code == 200:
                payload["sha"] = existing.json()["sha"]
            elif existing.status_code != 404:
                existing.raise_for_status()
            self._http.put(url, json=payload, headers=auth).raise_for_status()

        pr = self._http.post(
            f"{repo_path}/pulls",
            json={
                "title": title,
                "head": branch,
                "base": repo.json()["default_branch"],
                "body": body,
            },
            headers=auth,
        )
        pr.raise_for_status()
        return pr.json()["html_url"]

    def _installation_token(self, installation_id: int) -> str:
        response = self._http.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self._app_jwt()}"},
        )
        response.raise_for_status()
        return response.json()["token"]

    def _app_jwt(self) -> str:
        now = int(time.time())
        # Backdate iat to tolerate clock drift; GitHub caps exp at 10 minutes.
        claims = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}
        return jwt.encode(claims, self._private_key, algorithm="RS256")
