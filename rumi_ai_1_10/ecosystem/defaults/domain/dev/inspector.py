"""Dev Inspector — リクエストログの記録と取得を管理する。

インメモリ保存（MVP）。上限1000件で古いものから削除。
シングルトンパターン。
"""

import time
import threading
from collections import deque


class Inspector:
    """リクエストログの記録・取得を管理するシングルトン。"""

    _instance = None
    _lock = threading.Lock()
    MAX_LOGS = 1000

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._logs: deque = deque(maxlen=self.MAX_LOGS)
        self._index: dict[str, dict] = {}
        self._data_lock = threading.Lock()

    def log_request(
        self,
        request_id: str,
        conversation_id: str | None = None,
        model: str = "",
        prompt_used: str = "",
        tools_called: list | None = None,
        context_info: dict | None = None,
    ) -> dict:
        """リクエストログを記録する。

        Args:
            request_id:      リクエスト固有ID
            conversation_id: 会話ID (任意)
            model:           使用モデル名
            prompt_used:     使用されたプロンプト内容
            tools_called:    呼び出されたツール一覧
            context_info:    コンテキスト情報

        Returns:
            記録されたログ dict
        """
        entry = {
            "request_id": request_id,
            "conversation_id": conversation_id or "",
            "model": model,
            "prompt_used": prompt_used,
            "tools_called": list(tools_called or []),
            "context_info": dict(context_info or {}),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._data_lock:
            # deque の maxlen 超過分は自動削除される
            # ただし _index からも古いエントリを消す必要がある
            if len(self._logs) >= self.MAX_LOGS:
                oldest = self._logs[0]
                self._index.pop(oldest["request_id"], None)
            self._logs.append(entry)
            self._index[request_id] = entry
        return entry

    def get_log(self, request_id: str) -> dict | None:
        """特定の request_id のログを取得する。"""
        with self._data_lock:
            return self._index.get(request_id)

    def get_latest(self) -> dict | None:
        """最新のリクエストログを取得する。"""
        with self._data_lock:
            if self._logs:
                return self._logs[-1]
            return None

    def list_logs(self, limit: int = 20) -> list[dict]:
        """ログ一覧を新しい順で返す。

        Args:
            limit: 取得件数上限 (デフォルト20)

        Returns:
            ログ dict のリスト (新しい順)
        """
        with self._data_lock:
            result = list(self._logs)
            result.reverse()
            return result[:limit]

    def find_by_conversation(self, conversation_id: str, limit: int = 20) -> list[dict]:
        """特定の会話IDに紐づくログを新しい順で返す。"""
        with self._data_lock:
            result = [
                e for e in self._logs
                if e["conversation_id"] == conversation_id
            ]
            result.reverse()
            return result[:limit]

    def clear(self) -> None:
        """全ログをクリアする。"""
        with self._data_lock:
            self._logs.clear()
            self._index.clear()
