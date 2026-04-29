"""Git操作ドメインロジック."""

import os
import subprocess


class GitOps:
    """ワークスペース内の git 操作。"""

    def __init__(self, workspace_root=None):
        self._root = os.path.realpath(workspace_root or os.getcwd())

    def _run(self, args, timeout=30):
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

    def status(self):
        """リポジトリのステータスを返す。"""
        branch = self._run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        porcelain = self._run(["status", "--porcelain=v1"])
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
        }

    def diff(self, ref=None):
        """差分を返す。"""
        args = ["diff"]
        if ref:
            args.append(ref)
        diff = self._run(args)
        return {
            "diff": diff,
            "files_changed": len([line for line in diff.splitlines() if line.startswith("diff --git ")]),
        }

    def commit(self, message, all_tracked=False):
        """コミットを実行する。"""
        if all_tracked:
            self._run(["add", "-u"])
        output = self._run(["commit", "-m", message])
        commit_hash = self._run(["rev-parse", "--short", "HEAD"]).strip()
        return {
            "commit_hash": commit_hash,
            "message": message,
            "output": output,
        }

    def push(self, remote="origin", branch=None):
        """プッシュを実行する。"""
        args = ["push", remote]
        if branch:
            args.append(branch)
        output = self._run(args, timeout=120)
        return {
            "remote": remote,
            "branch": branch,
            "pushed": True,
            "output": output,
        }
