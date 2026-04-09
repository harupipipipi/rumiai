"""Git操作ドメインロジック（スタブ実装）

全メソッドは固定レスポンスを返す。
"""


class GitOps:
    """Git操作のスタブ実装。"""

    def status(self):
        """リポジトリのステータスを返す（スタブ）。"""
        return {
            "branch": "main",
            "clean": True,
            "staged": [],
            "modified": [],
            "untracked": [],
        }

    def diff(self, ref=None):
        """差分を返す（スタブ）。"""
        return {
            "diff": "",
            "files_changed": 0,
        }

    def commit(self, message):
        """コミットを実行する（スタブ）。"""
        return {
            "commit_hash": "abc1234",
            "message": message,
        }

    def push(self, remote="origin", branch=None):
        """プッシュを実行する（スタブ）。"""
        return {
            "remote": remote,
            "branch": branch or "main",
            "pushed": True,
        }
