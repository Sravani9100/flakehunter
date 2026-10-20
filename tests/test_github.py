import base64
import io
import json
import zipfile

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from flakehunter.github import GitHubClient, extract_xml_files, verify_signature


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_verify_signature():
    # Example from GitHub's webhook documentation.
    signature = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
    assert verify_signature("It's a Secret to Everybody", b"Hello, World!", signature)
    assert not verify_signature("wrong", b"Hello, World!", signature)
    assert not verify_signature("It's a Secret to Everybody", b"Hello, World!", None)


def test_extract_xml_files_skips_other_files():
    archive = make_zip({"report.xml": b"<a/>", "nested/more.xml": b"<b/>", "log.txt": b"x"})
    assert sorted(extract_xml_files(archive)) == [b"<a/>", b"<b/>"]


KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()


def test_open_pull_request_commits_files_on_a_new_branch():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path, method = request.url.path, request.method
        if path == "/app/installations/7/access_tokens":
            return httpx.Response(201, json={"token": "inst-token"})
        if (method, path) == ("GET", "/repos/acme/shop"):
            return httpx.Response(200, json={"default_branch": "main"})
        if (method, path) == ("POST", "/repos/acme/shop/git/refs"):
            return httpx.Response(201, json={})
        if path == "/repos/acme/shop/contents/tests/test_x.py":
            if method == "GET":
                return httpx.Response(200, json={"sha": "blob123"})
            return httpx.Response(200, json={})
        if path == "/repos/acme/shop/contents/src/new.py":
            return httpx.Response(404 if method == "GET" else 201, json={})
        if (method, path) == ("POST", "/repos/acme/shop/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/acme/shop/pull/9"})
        return httpx.Response(500)

    client = GitHubClient("123", PEM, transport=httpx.MockTransport(handler))
    url = client.open_pull_request(
        installation_id=7,
        repo_full_name="acme/shop",
        base_sha="abc123",
        branch="flakehunter/fix-1",
        files={"tests/test_x.py": "fixed\n", "src/new.py": "new\n"},
        title="Fix flaky test test_x",
        body="Body",
    )

    assert url == "https://github.com/acme/shop/pull/9"
    ref = next(r for r in requests if r.url.path.endswith("/git/refs"))
    assert json.loads(ref.content) == {"ref": "refs/heads/flakehunter/fix-1", "sha": "abc123"}
    puts = {r.url.path: json.loads(r.content) for r in requests if r.method == "PUT"}
    assert puts["/repos/acme/shop/contents/tests/test_x.py"]["sha"] == "blob123"
    assert "sha" not in puts["/repos/acme/shop/contents/src/new.py"]
    assert base64.b64decode(puts["/repos/acme/shop/contents/src/new.py"]["content"]) == b"new\n"
    pull = json.loads(requests[-1].content)
    assert (pull["head"], pull["base"]) == ("flakehunter/fix-1", "main")


def test_fetch_junit_reports_downloads_matching_artifacts():
    key, pem = KEY, PEM
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/app/installations/7/access_tokens":
            app_jwt = request.headers["Authorization"].removeprefix("Bearer ")
            claims = jwt.decode(app_jwt, key.public_key(), algorithms=["RS256"])
            assert claims["iss"] == "123"
            return httpx.Response(201, json={"token": "inst-token"})
        if path == "/repos/acme/shop/actions/runs/55/artifacts":
            return httpx.Response(
                200,
                json={
                    "artifacts": [
                        {
                            "name": "junit-results",
                            "expired": False,
                            "archive_download_url": "https://api.github.com/dl/1",
                        },
                        {
                            "name": "coverage",
                            "expired": False,
                            "archive_download_url": "https://api.github.com/dl/2",
                        },
                        {
                            "name": "test-results-old",
                            "expired": True,
                            "archive_download_url": "https://api.github.com/dl/3",
                        },
                    ]
                },
            )
        if path == "/dl/1":
            return httpx.Response(200, content=make_zip({"report.xml": b"<testsuites/>"}))
        return httpx.Response(404)

    client = GitHubClient("123", pem, transport=httpx.MockTransport(handler))
    reports = client.fetch_junit_reports(
        installation_id=7, repo_full_name="acme/shop", run_id=55, name_pattern="junit|test-results"
    )

    assert reports == [b"<testsuites/>"]
    assert [r.url.path for r in requests] == [
        "/app/installations/7/access_tokens",
        "/repos/acme/shop/actions/runs/55/artifacts",
        "/dl/1",
    ]
    assert requests[1].headers["Authorization"] == "Bearer inst-token"
