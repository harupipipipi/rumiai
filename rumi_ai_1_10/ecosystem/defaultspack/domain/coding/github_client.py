from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:pull|issues)/(?P<number>\d+)(?:[/?#].*)?$"
)


class GitHubClientError(RuntimeError):
    def __init__(self, message: str, code: str = "GITHUB_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GitHubRef:
    owner: str
    repo: str
    number: int

    @property
    def repo_full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_github_url(url: str) -> GitHubRef:
    match = GITHUB_URL_RE.match(str(url or "").strip())
    if not match:
        raise GitHubClientError("GitHub URL must look like https://github.com/owner/repo/pull/123 or /issues/123", "GITHUB_URL_INVALID")
    return GitHubRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


class GitHubReadClient:
    """Small read-only GitHub client with token-first REST and gh CLI fallback."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

    def pr(self, url: str) -> dict[str, Any]:
        ref = parse_github_url(url)
        pr = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}")
        files = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}/files")
        review_comments = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}/comments")
        issue_comments = self._api(f"repos/{ref.repo_full_name}/issues/{ref.number}/comments")
        checks = self.checks_for_pr_ref(ref, pr)
        return {
            "url": url,
            "repo": ref.repo_full_name,
            "number": ref.number,
            "title": pr.get("title", ""),
            "state": pr.get("state", ""),
            "author": (pr.get("user") or {}).get("login"),
            "base": (pr.get("base") or {}).get("ref"),
            "head": (pr.get("head") or {}).get("ref"),
            "head_sha": (pr.get("head") or {}).get("sha"),
            "metadata": pr,
            "files": files if isinstance(files, list) else [],
            "review_comments": review_comments if isinstance(review_comments, list) else [],
            "comments": issue_comments if isinstance(issue_comments, list) else [],
            "checks": checks,
        }

    def issue(self, url: str) -> dict[str, Any]:
        ref = parse_github_url(url)
        issue = self._api(f"repos/{ref.repo_full_name}/issues/{ref.number}")
        comments = self._api(f"repos/{ref.repo_full_name}/issues/{ref.number}/comments")
        return {
            "url": url,
            "repo": ref.repo_full_name,
            "number": ref.number,
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "author": (issue.get("user") or {}).get("login"),
            "metadata": issue,
            "comments": comments if isinstance(comments, list) else [],
        }

    def ci_status(self, url: str) -> dict[str, Any]:
        ref = parse_github_url(url)
        pr = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}")
        checks = self.checks_for_pr_ref(ref, pr)
        return {
            "url": url,
            "repo": ref.repo_full_name,
            "number": ref.number,
            "head_sha": (pr.get("head") or {}).get("sha"),
            "checks": checks,
        }

    def checks_for_pr_ref(self, ref: GitHubRef, pr: dict[str, Any]) -> dict[str, Any]:
        sha = str((pr.get("head") or {}).get("sha") or "").strip()
        if not sha:
            return {"check_runs": [], "statuses": [], "state": "unknown"}
        check_runs = self._api(f"repos/{ref.repo_full_name}/commits/{sha}/check-runs")
        statuses = self._api(f"repos/{ref.repo_full_name}/commits/{sha}/status")
        runs = check_runs.get("check_runs", []) if isinstance(check_runs, dict) else []
        combined_state = statuses.get("state", "unknown") if isinstance(statuses, dict) else "unknown"
        return {
            "head_sha": sha,
            "state": combined_state,
            "total_count": check_runs.get("total_count", len(runs)) if isinstance(check_runs, dict) else len(runs),
            "check_runs": runs,
            "statuses": statuses.get("statuses", []) if isinstance(statuses, dict) else [],
        }

    def _api(self, path: str) -> Any:
        if self.token:
            return self._api_with_token(path)
        return self._api_with_gh(path)

    def _api_with_token(self, path: str) -> Any:
        request = urllib.request.Request(
            "https://api.github.com/" + path.lstrip("/"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "RumiAI-defaultspack",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubClientError(f"GitHub API failed with HTTP {exc.code}: {detail}", "GITHUB_API_ERROR") from exc
        except urllib.error.URLError as exc:
            raise GitHubClientError(f"GitHub API network error: {exc}", "GITHUB_NETWORK_ERROR") from exc

    def _api_with_gh(self, path: str) -> Any:
        gh = shutil.which("gh")
        if not gh:
            raise GitHubClientError("Set GITHUB_TOKEN or GH_TOKEN, or install/authenticate gh CLI for GitHub read workflow.", "GITHUB_TOKEN_REQUIRED")
        try:
            auth = subprocess.run([gh, "auth", "status"], text=True, capture_output=True, timeout=15)
        except Exception as exc:
            raise GitHubClientError("Set GITHUB_TOKEN or GH_TOKEN; gh CLI auth could not be checked.", "GITHUB_TOKEN_REQUIRED") from exc
        if auth.returncode != 0:
            raise GitHubClientError("Set GITHUB_TOKEN or GH_TOKEN, or run gh auth login for GitHub read workflow.", "GITHUB_TOKEN_REQUIRED")
        completed = subprocess.run(
            [gh, "api", path.lstrip("/")],
            text=True,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise GitHubClientError(completed.stderr.strip() or "gh api failed", "GITHUB_API_ERROR")
        try:
            return json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise GitHubClientError("gh api returned invalid JSON", "GITHUB_API_ERROR") from exc
