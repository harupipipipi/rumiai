"""Git操作ドメインロジック."""

import os
import shlex
import subprocess

from .workspace_jail import WorkspaceJail


class GitOps:
    """ワークスペース内の git 操作。"""

    def __init__(self, workspace_root=None):
        self._root = os.path.realpath(workspace_root or os.getcwd())
        self._jail = WorkspaceJail(self._root)

    def _run(self, args, timeout=30):
        self.assert_git_root_inside_workspace()
        completed = subprocess.run(
            ["git"] + list(args),
            cwd=self._root,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
        return completed.stdout

    def _run_raw(self, args, timeout=30):
        completed = subprocess.run(
            ["git"] + list(args),
            cwd=self._root,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
        return completed.stdout

    def git_root(self):
        return os.path.realpath(self._run_raw(["rev-parse", "--show-toplevel"]).strip())

    def assert_git_root_inside_workspace(self):
        if getattr(self, "_checking_git_root", False):
            return True
        self._checking_git_root = True
        try:
            root = self.git_root()
        finally:
            self._checking_git_root = False
        if root != self._root and not root.startswith(self._root + os.sep):
            raise ValueError("git root is outside workspace root: " + root)
        return True

    def _is_visible_git_path(self, path):
        return self._jail.restriction_reason(path) is None

    @staticmethod
    def _normalize_git_status_path(path):
        text = str(path or "").strip()
        if not text:
            return ""
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = []
        if len(parts) == 1:
            return parts[0]
        return text.strip('"')

    def _porcelain_v1_paths(self, path_text):
        return tuple(
            normalized
            for normalized in (
                self._normalize_git_status_path(part)
                for part in str(path_text or "").split(" -> ")
            )
            if normalized
        )

    def _visible_porcelain_v1_path(self, path_text):
        paths = self._porcelain_v1_paths(path_text)
        return bool(paths) and all(self._is_visible_git_path(path) for path in paths)

    def _porcelain_v2_paths(self, line):
        text = str(line or "")
        if text.startswith("#"):
            return ()
        if text.startswith(("? ", "! ")):
            return (self._normalize_git_status_path(text[2:]),)
        if text.startswith("1 "):
            parts = text.split(maxsplit=8)
            return (self._normalize_git_status_path(parts[8]),) if len(parts) > 8 else ()
        if text.startswith("2 "):
            parts = text.split(maxsplit=9)
            if len(parts) <= 9:
                return ()
            return tuple(
                normalized
                for normalized in (
                    self._normalize_git_status_path(part)
                    for part in parts[9].split("\t")
                )
                if normalized
            )
        if text.startswith("u "):
            parts = text.split(maxsplit=10)
            return (self._normalize_git_status_path(parts[10]),) if len(parts) > 10 else ()
        parts = text.split()
        return (self._normalize_git_status_path(parts[-1]),) if parts else ()

    def _visible_porcelain_v2_line(self, line):
        paths = self._porcelain_v2_paths(line)
        return str(line).startswith("#") or (bool(paths) and all(self._is_visible_git_path(path) for path in paths))

    def _run_diff_for_files(self, files, ref=None, stat=False):
        chunks = []
        for path in files:
            args = ["diff"]
            if stat:
                args.append("--stat")
            if ref:
                args.append(ref)
            args.extend(["--", path])
            output = self._run(args)
            if output:
                chunks.append(output)
        return "".join(chunks)

    def status(self):
        """リポジトリのステータスを返す。"""
        branch = self._run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        porcelain = self._run(["status", "--porcelain=v1"])
        porcelain_v2 = self._run(["status", "--porcelain=v2", "--branch"])
        staged = []
        modified = []
        untracked = []
        for line in porcelain.splitlines():
            if not line:
                continue
            index_status = line[0]
            worktree_status = line[1]
            paths = self._porcelain_v1_paths(line[3:])
            if not paths or not all(self._is_visible_git_path(path) for path in paths):
                continue
            path = paths[-1]
            if line.startswith("?? "):
                untracked.append(path)
            elif index_status != " ":
                staged.append(path)
            elif worktree_status != " ":
                modified.append(path)
        filtered_porcelain = "\n".join(
            line
            for line in porcelain.splitlines()
            if len(line) < 4 or self._visible_porcelain_v1_path(line[3:])
        )
        filtered_porcelain_v2 = "\n".join(
            line
            for line in porcelain_v2.splitlines()
            if self._visible_porcelain_v2_line(line)
        )
        return {
            "branch": branch,
            "clean": not (staged or modified or untracked),
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "porcelain": filtered_porcelain + ("\n" if filtered_porcelain else ""),
            "porcelain_v2": filtered_porcelain_v2 + ("\n" if filtered_porcelain_v2 else ""),
        }

    def branch(self, action="current", name=None, create=False):
        """ブランチ情報の取得、またはブランチ切り替えを行う。"""
        action = action or "current"
        if action == "current":
            current = self._run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
            branches = [
                line.strip().lstrip("* ").strip()
                for line in self._run(["branch", "--format", "%(refname:short)"]).splitlines()
                if line.strip()
            ]
            return {"branch": current, "branches": branches}
        if action == "list":
            current = self._run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
            branches = [
                line.strip()
                for line in self._run(["branch", "--format", "%(refname:short)"]).splitlines()
                if line.strip()
            ]
            return {"branch": current, "branches": branches}
        if action == "switch":
            if not name:
                raise ValueError("branch name is required")
            args = ["switch"]
            if create:
                args.append("-c")
            args.append(name)
            output = self._run(args)
            return {"branch": name, "switched": True, "created": bool(create), "output": output}
        raise ValueError("unsupported branch action: " + str(action))

    def diff(self, ref=None):
        """差分を返す。"""
        args = ["diff"]
        if ref:
            args.append(ref)
        name_args = ["diff", "--name-only"]
        if ref:
            name_args.append(ref)
        names = self._run(name_args)
        visible_files = [line for line in names.splitlines() if line.strip() and self._is_visible_git_path(line)]
        diff = self._run_diff_for_files(visible_files, ref=ref)
        stat = self._run_diff_for_files(visible_files, ref=ref, stat=True)
        return {
            "diff": diff,
            "stat": stat,
            "files": visible_files,
            "files_changed": len([line for line in diff.splitlines() if line.startswith("diff --git ")]),
        }

    def commit(self, message, all_tracked=False, paths=None, files=None):
        """コミットを実行する。

        paths / files: list[str] — 指定ファイルだけstageしてcommitする。
        all_tracked: bool — git add -u で全trackedファイルをstageする。
        paths (or files) と all_tracked=True の併用は禁止。
        .env 等の restricted path は WorkspaceRestrictedPath を送出。
        ../ traversal は WorkspacePathViolation を送出。
        """
        selected = paths if paths is not None else files
        if selected is not None and all_tracked:
            raise ValueError("paths/files and all_tracked=True cannot be used together")
        if selected is not None:
            if not isinstance(selected, (list, tuple)) or not selected:
                raise ValueError("paths/files must be a non-empty list of strings")
            for p in selected:
                if not isinstance(p, str) or not p.strip():
                    raise ValueError("each path must be a non-empty string")
                normalized = p.replace("\\", "/").strip()
                parts = [part for part in normalized.split("/") if part and part != "."]
                if any(part == ".." for part in parts):
                    from .workspace_jail import WorkspacePathViolation
                    raise WorkspacePathViolation(
                        f"Path traversal detected: '{p}' resolves outside workspace root"
                    )
                self._jail.ensure_allowed(normalized, operation="git commit")
            self._run(["add", "--", *selected])
        elif all_tracked:
            self._run(["add", "-u"])
        if self.status()["clean"]:
            raise RuntimeError("nothing to commit")
        output = self._run(["commit", "-m", message])
        commit_hash = self._run(["rev-parse", "--short", "HEAD"]).strip()
        return {
            "commit_hash": commit_hash,
            "message": message,
            "output": output,
            "paths": list(selected) if selected else None,
        }

    def push(self, remote="origin", branch=None, dry_run=False):
        """プッシュを実行する。"""
        args = ["push", remote]
        if branch:
            args.append(branch)
        if dry_run:
            args.append("--dry-run")
        output = self._run(args, timeout=120)
        return {
            "remote": remote,
            "branch": branch,
            "pushed": not dry_run,
            "dry_run": bool(dry_run),
            "output": output,
        }
