"""ターミナル操作ドメインロジック（スタブ実装）

実際のsubprocess実行は行わず、コマンド文字列を記録して固定レスポンスを返す。
"""

import uuid


class Terminal:
    """ターミナル操作のスタブ実装。"""

    def __init__(self):
        self._history = []

    @property
    def history(self):
        """実行履歴を返す。"""
        return list(self._history)

    def execute(self, command, cwd=None, timeout=30):
        """コマンド実行スタブ。

        コマンド文字列を記録し、固定レスポンスを返す。
        実際のsubprocess実行はしない。
        """
        record = {
            "type": "execute",
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
        }
        self._history.append(record)
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        }

    def stream(self, command, cwd=None):
        """ストリーム実行スタブ。

        コマンド文字列を記録し、stream_idを返す。
        実際の実行はしない。
        """
        stream_id = str(uuid.uuid4())
        record = {
            "type": "stream",
            "command": command,
            "cwd": cwd,
            "stream_id": stream_id,
        }
        self._history.append(record)
        return {
            "command": command,
            "stream_id": stream_id,
            "started": True,
        }
