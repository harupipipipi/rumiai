from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_github_url_parser_accepts_pull_and_issue_urls():
    from domain.coding.github_client import parse_github_url

    pull = parse_github_url("https://github.com/openai/codex/pull/123")
    issue = parse_github_url("https://github.com/openai/codex/issues/456#comment")

    assert pull.repo_full_name == "openai/codex"
    assert pull.number == 123
    assert issue.repo_full_name == "openai/codex"
    assert issue.number == 456


def test_github_read_block_is_approval_gated(tmp_path, monkeypatch):
    from blocks.coding.github_pr_read import run as pr_read_run
    from domain.safety.approval import reset_approval_state_for_tests

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    reset_approval_state_for_tests()

    result = pr_read_run({"url": "https://github.com/openai/codex/pull/123"}, {})

    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
    assert result["data"]["operation"] == "github.pr_read"
    assert result["data"]["reason"] == "network"


def test_github_client_reports_clear_token_setup_error(monkeypatch):
    import domain.coding.github_client as github_client

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(github_client.shutil, "which", lambda name: None)

    with pytest.raises(github_client.GitHubClientError) as exc:
        github_client.GitHubReadClient().issue("https://github.com/openai/codex/issues/456")

    assert exc.value.code == "GITHUB_TOKEN_REQUIRED"
    assert "GITHUB_TOKEN" in str(exc.value)


def test_github_pr_read_returns_metadata_files_comments_and_checks(monkeypatch):
    from blocks.coding import github_pr_read

    class FakeGitHubClient:
        def pr(self, url):
            return {
                "url": url,
                "repo": "openai/codex",
                "number": 123,
                "title": "Ship cockpit",
                "files": [{"filename": "app.py"}],
                "review_comments": [{"body": "review"}],
                "comments": [{"body": "issue"}],
                "checks": {"state": "success", "check_runs": []},
            }

    monkeypatch.setattr(github_pr_read, "GitHubReadClient", lambda: FakeGitHubClient())

    result = github_pr_read.run(
        {"url": "https://github.com/openai/codex/pull/123"},
        {"_tool_server_approved": True},
    )

    assert result["status"] == "ok"
    assert result["data"]["title"] == "Ship cockpit"
    assert result["data"]["files"][0]["filename"] == "app.py"
    assert result["data"]["review_comments"][0]["body"] == "review"
    assert result["data"]["checks"]["state"] == "success"


def test_github_token_client_follows_link_pagination_for_lists(monkeypatch):
    import domain.coding.github_client as github_client

    class FakeResponse:
        def __init__(self, payload, link=""):
            self.payload = payload
            self.headers = {"Link": link}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    seen_urls = []

    def fake_urlopen(request, timeout):
        del timeout
        seen_urls.append(request.full_url)
        if "page=2" in request.full_url:
            return FakeResponse([{"filename": "second.py"}])
        return FakeResponse(
            [{"filename": "first.py"}],
            '<https://api.github.com/repos/openai/codex/pulls/123/files?per_page=100&page=2>; rel="next"',
        )

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake_urlopen)

    files = github_client.GitHubReadClient(token="tok")._api(
        "repos/openai/codex/pulls/123/files?per_page=100"
    )

    assert [item["filename"] for item in files] == ["first.py", "second.py"]
    assert seen_urls[1].endswith("page=2")


def test_github_token_client_merges_paginated_check_runs(monkeypatch):
    import domain.coding.github_client as github_client

    class FakeResponse:
        def __init__(self, payload, link=""):
            self.payload = payload
            self.headers = {"Link": link}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        if "page=2" in request.full_url:
            return FakeResponse({"total_count": 2, "check_runs": [{"name": "second"}]})
        return FakeResponse(
            {"total_count": 2, "check_runs": [{"name": "first"}]},
            '<https://api.github.com/repos/openai/codex/commits/abc/check-runs?per_page=100&page=2>; rel="next"',
        )

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake_urlopen)

    checks = github_client.GitHubReadClient(token="tok")._api(
        "repos/openai/codex/commits/abc/check-runs?per_page=100"
    )

    assert checks["total_count"] == 2
    assert [item["name"] for item in checks["check_runs"]] == ["first", "second"]
