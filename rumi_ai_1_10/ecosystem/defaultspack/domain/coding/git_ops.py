"""Git操作ドメインロジック."""

import os
import subprocess


class GitOps:
    """ワークスペース内の git 操作。"""

    def __init__(self, workspace_root=None):
        self._root = os.path.realpath(workspace_root or os.getcwd())

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
            path = line[3:]
            if line.startswith("?? "):
                untracked.append(path)
            elif index_status != " ":
                staged.append(path)
            elif worktree_status != " ":
                modified.append(path)
        return {
            "branch": branch,
            "clean": not (staged or modified or untracked),
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "porcelain": porcelain,
            "porcelain_v2": porcelain_v2,
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
        diff = self._run(args)
        stat_args = ["diff", "--stat"]
        name_args = ["diff", "--name-only"]
        if ref:
            stat_args.append(ref)
            name_args.append(ref)
        stat = self._run(stat_args)
        names = self._run(name_args)
        return {
            "diff": diff,
            "stat": stat,
            "files": [line for line in names.splitlines() if line.strip()],
            "files_changed": len([line for line in diff.splitlines() if line.startswith("diff --git ")]),
        }

    def commit(self, message, all_tracked=False):
        """コミットを実行する。"""
        if all_tracked:
            self._run(["add", "-u"])
        if self.status()["clean"]:
            raise RuntimeError("nothing to commit")
        output = self._run(["commit", "-m", message])
        commit_hash = self._run(["rev-parse", "--short", "HEAD"]).strip()
        return {
            "commit_hash": commit_hash,
            "message": message,
            "output": output,
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
