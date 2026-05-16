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
        files = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}/files?per_page=100")
        review_comments = self._api(f"repos/{ref.repo_full_name}/pulls/{ref.number}/comments?per_page=100")
        issue_comments = self._api(f"repos/{ref.repo_full_name}/issues/{ref.number}/comments?per_page=100")
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
        comments = self._api(f"repos/{ref.repo_full_name}/issues/{ref.number}/comments?per_page=100")
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
        check_runs = self._api(f"repos/{ref.repo_full_name}/commits/{sha}/check-runs?per_page=100")
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
        url = "https://api.github.com/" + path.lstrip("/")
        pages = []
        try:
            while url:
                request = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "RumiAI-defaultspack",
                    },
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    pages.append(json.loads(response.read().decode("utf-8")))
                    url = _next_link(response.headers.get("Link", ""))
            return _merge_paginated_payloads(pages)
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
            [gh, "api", "--paginate", "--slurp", path.lstrip("/")],
            text=True,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise GitHubClientError(completed.stderr.strip() or "gh api failed", "GITHUB_API_ERROR")
        try:
            payload = json.loads(completed.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise GitHubClientError("gh api returned invalid JSON", "GITHUB_API_ERROR") from exc
        if isinstance(payload, list):
            return _merge_paginated_payloads(payload)
        return payload


def _next_link(link_header: str) -> str:
    for part in str(link_header or "").split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        match = re.match(r"<([^>]+)>", section)
        if match:
            return match.group(1)
    return ""


def _merge_paginated_payloads(pages: list[Any]) -> Any:
    pages = [page for page in pages if page is not None]
    if not pages:
        return {}
    first = pages[0]
    if len(pages) == 1:
        return first
    if all(isinstance(page, list) for page in pages):
        merged: list[Any] = []
        for page in pages:
            merged.extend(page)
        return merged
    if all(isinstance(page, dict) for page in pages):
        list_key = _paginated_dict_list_key(pages)
        if list_key:
            merged_dict = dict(first)
            merged_items: list[Any] = []
            for page in pages:
                merged_items.extend(page.get(list_key, []))
            merged_dict[list_key] = merged_items
            if "total_count" in merged_dict:
                merged_dict["total_count"] = max(int(merged_dict.get("total_count") or 0), len(merged_items))
            return merged_dict
    return first


def _paginated_dict_list_key(pages: list[dict[str, Any]]) -> str:
    candidate_keys = ("check_runs", "statuses", "jobs", "workflow_runs")
    for key in candidate_keys:
        if all(isinstance(page.get(key), list) for page in pages):
            return key
    return ""
