"""
interface_registry.py - 提供物登録箱(用途名固定しない)

Step1では「複数登録できる」「取得戦略を選べる」最小実装を用意する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal, Callable, Iterable


GetStrategy = Literal["first", "last", "all"]


@dataclass
class InterfaceRegistry:
    """
    提供物の登録箱。

    設計(確定仕様):
    - tool/prompt/ai_client 等の用途名をKernelが固定しないため、
      "何でも登録できる箱" を提供する。
    - 同一キーへの複数登録を許可する(OS的な拡張に強い)。
    """

    _store: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register(self, key: str, value: Any, meta: Optional[Dict[str, Any]] = None) -> None:
        # metaが壊れていても落とさない(fail-soft)
        meta_dict: Dict[str, Any]
        if meta is None:
            meta_dict = {}
        elif isinstance(meta, dict):
            meta_dict = dict(meta)
        else:
            meta_dict = {"_raw_meta": meta}

        entry = {
            "key": key,
            "value": value,
            "meta": meta_dict,
            "ts": self._now_ts(),
        }
        self._store.setdefault(key, []).append(entry)

    def get(self, key: str, strategy: GetStrategy = "last") -> Any:
        items = self._store.get(key, [])
        if not items:
            return None

        if strategy == "first":
            return items[0]["value"]
        if strategy == "last":
            return items[-1]["value"]
        if strategy == "all":
            return [it["value"] for it in items]

        # 不明なstrategyはlastにフォールバック
        return items[-1]["value"]

    def list(self, prefix: Optional[str] = None, include_meta: bool = False) -> Dict[str, Any]:
        """
        登録状況を列挙する。
        - include_meta=False: {key: count}
        - include_meta=True:  {key: {"count": n, "last_ts": "...", "last_meta": {...}}}
        """
        keys: Iterable[str]
        if prefix is None:
            keys = self._store.keys()
        else:
            keys = [k for k in self._store.keys() if k.startswith(prefix)]

        if not include_meta:
            return {k: len(self._store.get(k, [])) for k in keys}

        out: Dict[str, Any] = {}
        for k in keys:
            items = self._store.get(k, [])
            last = items[-1] if items else None
            out[k] = {
                "count": len(items),
                "last_ts": last.get("ts") if last else None,
                "last_meta": last.get("meta") if last else None,
            }
        return out

    def find(self, predicate: Callable[[str, Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        """
        用途名を固定しない探索API。
        predicate(key, entry) が True の entry を列挙する。
        """
        results: List[Dict[str, Any]] = []
        for k, items in self._store.items():
            for entry in items:
                try:
                    if predicate(k, entry):
                        results.append(entry)
                except Exception:
                    # 探索中のpredicate例外は fail-soft で無視
                    continue
        return results

    def unregister(self, key: str, predicate: Optional[Callable[[Dict[str, Any]], bool]] = None) -> int:
        """
        登録解除。
        - predicate無し: key配下を全削除
        - predicateあり: 条件一致のみ削除
        戻り値: 削除件数
        """
        if key not in self._store:
            return 0
        if predicate is None:
            count = len(self._store[key])
            del self._store[key]
            return count

        items = self._store.get(key, [])
        kept: List[Dict[str, Any]] = []
        removed = 0
        for entry in items:
            try:
                if predicate(entry):
                    removed += 1
                else:
                    kept.append(entry)
            except Exception:
                # predicate例外は安全側(削除しない)
                kept.append(entry)
        self._store[key] = kept
        if not self._store[key]:
            del self._store[key]
        return removed
