"""Dev UsageTracker — プロンプト使用状況のトラッキングを管理する。

Inspector を変更せず、独立したシングルトンとして動作する。

機能:
    - 各プロンプトの呼び出し回数・最終使用日時の記録
    - 会話⇔プロンプトのマッピング
    - プロンプトレンダリング結果の履歴保持（直近N件）
    - 編集履歴の保持（ロールバック用）

インメモリ保存。スレッドセーフ。
"""

import time
import threading
from collections import defaultdict, deque


class UsageTracker:
    """プロンプト使用状況をトラッキングするシングルトン。"""

    _instance = None
    _lock = threading.Lock()
    MAX_RENDER_HISTORY = 50
    MAX_EDIT_HISTORY = 30

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
        self._data_lock = threading.Lock()

        # prompt_name -> {"call_count": int, "last_used": str}
        self._usage_stats: dict[str, dict] = {}

        # conversation_id -> set of prompt_names
        self._conversation_prompts: dict[str, set] = defaultdict(set)

        # prompt_name -> deque of {"rendered": str, "variables": dict, "timestamp": str}
        self._render_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=UsageTracker.MAX_RENDER_HISTORY)
        )

        # prompt_name -> deque of {"body_before": str, "body_after": str, "timestamp": str, "edit_id": str}
        self._edit_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=UsageTracker.MAX_EDIT_HISTORY)
        )

        # 自動インクリメントする編集ID用カウンタ
        self._edit_counter: int = 0

    # ------------------------------------------------------------------
    # 使用状況の記録
    # ------------------------------------------------------------------

    def record_usage(
        self,
        prompt_name: str,
        conversation_id: str = "",
        rendered_content: str = "",
        variables: dict | None = None,
    ) -> dict:
        """プロンプトの使用を1件記録する。

        Args:
            prompt_name:      使用されたプロンプト名
            conversation_id:  会話ID
            rendered_content: レンダリング結果の文字列
            variables:        レンダリングに使用された変数

        Returns:
            記録された使用状況 dict
        """
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._data_lock:
            # 呼び出し回数・最終使用日時
            if prompt_name not in self._usage_stats:
                self._usage_stats[prompt_name] = {
                    "call_count": 0,
                    "last_used": "",
                    "first_used": now,
                }
            self._usage_stats[prompt_name]["call_count"] += 1
            self._usage_stats[prompt_name]["last_used"] = now

            # 会話⇔プロンプトマッピング
            if conversation_id:
                self._conversation_prompts[conversation_id].add(prompt_name)

            # レンダリング結果履歴
            render_entry = {
                "rendered": rendered_content,
                "variables": dict(variables or {}),
                "conversation_id": conversation_id,
                "timestamp": now,
            }
            self._render_history[prompt_name].append(render_entry)

        return {
            "prompt_name": prompt_name,
            "conversation_id": conversation_id,
            "timestamp": now,
            "call_count": self._usage_stats[prompt_name]["call_count"],
        }

    # ------------------------------------------------------------------
    # 使用統計の取得
    # ------------------------------------------------------------------

    def get_stats(self, prompt_name: str) -> dict | None:
        """特定プロンプトの使用統計を返す。

        Returns:
            {"prompt_name": str, "call_count": int, "last_used": str, "first_used": str}
            存在しなければ None
        """
        with self._data_lock:
            stats = self._usage_stats.get(prompt_name)
            if stats is None:
                return None
            return {
                "prompt_name": prompt_name,
                "call_count": stats["call_count"],
                "last_used": stats["last_used"],
                "first_used": stats["first_used"],
            }

    def get_all_stats(self) -> list[dict]:
        """全プロンプトの使用統計を呼び出し回数降順で返す。

        Returns:
            [{"prompt_name": str, "call_count": int, "last_used": str, "first_used": str}, ...]
        """
        with self._data_lock:
            result = []
            for name, stats in self._usage_stats.items():
                result.append({
                    "prompt_name": name,
                    "call_count": stats["call_count"],
                    "last_used": stats["last_used"],
                    "first_used": stats["first_used"],
                })
        result.sort(key=lambda x: x["call_count"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # 会話⇔プロンプトマッピング
    # ------------------------------------------------------------------

    def get_prompts_for_conversation(self, conversation_id: str) -> list[str]:
        """特定の会話で使われたプロンプト名一覧を返す。"""
        with self._data_lock:
            return sorted(self._conversation_prompts.get(conversation_id, set()))

    def get_conversations_for_prompt(self, prompt_name: str) -> list[str]:
        """特定のプロンプトが使われた会話ID一覧を返す。"""
        with self._data_lock:
            result = []
            for conv_id, prompts in self._conversation_prompts.items():
                if prompt_name in prompts:
                    result.append(conv_id)
            return sorted(result)

    def get_conversation_map(self) -> dict[str, list[str]]:
        """全会話⇔プロンプトマッピングを返す。

        Returns:
            {conversation_id: [prompt_name, ...], ...}
        """
        with self._data_lock:
            return {
                conv_id: sorted(prompts)
                for conv_id, prompts in self._conversation_prompts.items()
            }

    # ------------------------------------------------------------------
    # レンダリング結果履歴
    # ------------------------------------------------------------------

    def get_render_history(self, prompt_name: str, limit: int = 10) -> list[dict]:
        """特定プロンプトのレンダリング結果履歴を新しい順で返す。

        Args:
            prompt_name: プロンプト名
            limit:       取得件数上限

        Returns:
            [{"rendered": str, "variables": dict, "conversation_id": str, "timestamp": str}, ...]
        """
        with self._data_lock:
            history = list(self._render_history.get(prompt_name, []))
        history.reverse()
        return history[:limit]

    # ------------------------------------------------------------------
    # 編集履歴
    # ------------------------------------------------------------------

    def record_edit(
        self,
        prompt_name: str,
        body_before: str,
        body_after: str,
    ) -> dict:
        """プロンプト編集を1件記録する（ロールバック用）。

        Args:
            prompt_name: プロンプト名
            body_before: 編集前の本文
            body_after:  編集後の本文

        Returns:
            記録された編集履歴エントリ dict
        """
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._data_lock:
            self._edit_counter += 1
            edit_id = f"edit-{self._edit_counter}"
            entry = {
                "edit_id": edit_id,
                "prompt_name": prompt_name,
                "body_before": body_before,
                "body_after": body_after,
                "timestamp": now,
            }
            self._edit_history[prompt_name].append(entry)
        return entry

    def get_edit_history(self, prompt_name: str, limit: int = 10) -> list[dict]:
        """特定プロンプトの編集履歴を新しい順で返す。

        Args:
            prompt_name: プロンプト名
            limit:       取得件数上限

        Returns:
            [{"edit_id": str, "prompt_name": str, "body_before": str,
              "body_after": str, "timestamp": str}, ...]
        """
        with self._data_lock:
            history = list(self._edit_history.get(prompt_name, []))
        history.reverse()
        return history[:limit]

    def get_edit_by_id(self, prompt_name: str, edit_id: str) -> dict | None:
        """特定の編集IDに対応する編集履歴エントリを返す。

        Returns:
            編集履歴エントリ dict。見つからなければ None。
        """
        with self._data_lock:
            for entry in self._edit_history.get(prompt_name, []):
                if entry["edit_id"] == edit_id:
                    return dict(entry)
        return None

    def get_latest_edit(self, prompt_name: str) -> dict | None:
        """特定プロンプトの最新の編集履歴エントリを返す。

        Returns:
            編集履歴エントリ dict。存在しなければ None。
        """
        with self._data_lock:
            history = self._edit_history.get(prompt_name)
            if history and len(history) > 0:
                return dict(history[-1])
        return None

    # ------------------------------------------------------------------
    # Inspector からの一括取り込み
    # ------------------------------------------------------------------

    def sync_from_inspector(self, inspector) -> int:
        """Inspector の既存ログから使用状況を一括取り込みする。

        既に記録済みのデータとの重複は呼び出し回数に加算されるため、
        初回の同期時に一度だけ呼ぶことを推奨する。

        Args:
            inspector: Inspector インスタンス

        Returns:
            取り込んだログ件数
        """
        logs = inspector.list_logs(limit=1000)
        count = 0
        for log in logs:
            prompt_used = log.get("prompt_used", "")
            if not prompt_used:
                continue
            prompt_name = self._extract_prompt_name(prompt_used)
            self.record_usage(
                prompt_name=prompt_name,
                conversation_id=log.get("conversation_id", ""),
                rendered_content=prompt_used,
                variables=log.get("context_info", {}),
            )
            count += 1
        return count

    @staticmethod
    def _extract_prompt_name(prompt_used: str) -> str:
        """prompt_used 文字列からプロンプト名を推定する。

        単純なヒューリスティック: 最初の行またはプロンプト全体が短い場合はそれ自体を名前とし、
        長い場合は先頭80文字 + "..." で識別する。
        """
        if not prompt_used:
            return "(empty)"
        first_line = prompt_used.split("\n", 1)[0].strip()
        if len(first_line) <= 80:
            return first_line
        return first_line[:80] + "..."

    # ------------------------------------------------------------------
    # クリア
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """全データをクリアする。"""
        with self._data_lock:
            self._usage_stats.clear()
            self._conversation_prompts.clear()
            self._render_history.clear()
            self._edit_history.clear()
            self._edit_counter = 0
