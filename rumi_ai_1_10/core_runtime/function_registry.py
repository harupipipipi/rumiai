"""
function_registry.py - Function レジストリ

Pack 内の functions/ ディレクトリに格納された Function を
登録・検索・管理する中央レジストリ。

W24-FIX: Agent A テスト互換 + registry.py _load_functions() 互換

Usage:
    from core_runtime.function_registry import FunctionRegistry, FunctionEntry

    reg = FunctionRegistry(vocab_registry=vocab)
    reg.register(entry)
    reg.register(pack_id="pk", function_id="fn", manifest={...}, function_dir=Path(...))
    result = reg.get("pk:fn")
"""

from __future__ import annotations

import difflib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =====================================================================
# データクラス
# =====================================================================

@dataclass
class FunctionEntry:
    """Function の登録情報"""
    function_id: str
    pack_id: str
    description: str = ""
    requires: List[str] = field(default_factory=list)
    caller_requires: List[str] = field(default_factory=list)
    host_execution: bool = False
    tags: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    function_dir: Any = None  # Path or str
    main_py_path: Any = None  # Path or str
    manifest: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.pack_id}:{self.function_id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qualified_name": self.qualified_name,
            "function_id": self.function_id,
            "pack_id": self.pack_id,
            "description": self.description,
            "requires": list(self.requires),
            "caller_requires": list(self.caller_requires),
            "host_execution": self.host_execution,
            "tags": list(self.tags),
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "function_dir": str(self.function_dir) if self.function_dir else None,
            "main_py_path": str(self.main_py_path) if self.main_py_path else None,
        }


@dataclass
class BulkRegisterResult:
    """register_pack() の結果"""
    success: bool = True
    registered: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


# =====================================================================
# FunctionRegistry
# =====================================================================

class FunctionRegistry:
    """
    Function レジストリ。

    スレッドセーフ（RLock 使用）。
    VocabRegistry と連携してタグ正規化・同義語検索を行う。
    """

    def __init__(self, vocab_registry: Any = None) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, FunctionEntry] = {}  # qualified_name -> entry
        self._tag_index: Dict[str, set] = {}  # tag -> {qualified_name, ...}
        self._vocab_registry = vocab_registry

    # -----------------------------------------------------------------
    # 内部ヘルパー
    # -----------------------------------------------------------------

    def _normalize_tag(self, tag: str) -> str:
        """タグを正規化する。vocab_registry があれば resolve を使う。"""
        if self._vocab_registry is not None:
            try:
                return self._vocab_registry.resolve(tag, to_preferred=True)
            except Exception:
                pass
        return tag.strip().lower()

    def _add_to_tag_index(self, entry: FunctionEntry) -> None:
        for raw_tag in entry.tags:
            tag = self._normalize_tag(raw_tag)
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry.qualified_name)

    def _remove_from_tag_index(self, entry: FunctionEntry) -> None:
        for raw_tag in entry.tags:
            tag = self._normalize_tag(raw_tag)
            if tag in self._tag_index:
                self._tag_index[tag].discard(entry.qualified_name)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]

    @staticmethod
    def _entry_from_kwargs(
        pack_id: str,
        function_id: str,
        manifest: Dict[str, Any],
        function_dir: Any,
    ) -> FunctionEntry:
        """registry.py の _load_functions() が渡すキーワード引数から FunctionEntry を構築する。"""
        m = manifest or {}
        main_py = None
        if function_dir is not None:
            candidate = Path(function_dir) / "main.py"
            if candidate.exists():
                main_py = candidate

        return FunctionEntry(
            function_id=function_id,
            pack_id=pack_id,
            description=m.get("description", ""),
            requires=m.get("requires", []),
            caller_requires=m.get("caller_requires", []),
            host_execution=m.get("host_execution", False),
            tags=m.get("tags", []),
            input_schema=m.get("input_schema", {}),
            output_schema=m.get("output_schema", {}),
            function_dir=function_dir,
            main_py_path=main_py,
            manifest=m,
        )

    # -----------------------------------------------------------------
    # 登録
    # -----------------------------------------------------------------

    def register(
        self,
        entry: Any = None,
        *,
        pack_id: Optional[str] = None,
        function_id: Optional[str] = None,
        manifest: Optional[Dict[str, Any]] = None,
        function_dir: Any = None,
    ) -> bool:
        """
        Function を登録する。

        パターン 1 (Agent A): register(entry: FunctionEntry) -> bool
        パターン 2 (registry.py): register(pack_id=..., function_id=..., manifest=..., function_dir=...) -> bool

        Returns:
            True: 登録成功, False: 重複でスキップ

        Raises:
            TypeError: entry が FunctionEntry でも None でもなくキーワード引数もない
            ValueError: function_id / pack_id が空
        """
        # --- パターン分岐 ---
        if entry is not None:
            if not isinstance(entry, FunctionEntry):
                raise TypeError(
                    f"Expected FunctionEntry, got {type(entry).__name__}"
                )
            resolved_entry = entry
        elif pack_id is not None and function_id is not None:
            resolved_entry = self._entry_from_kwargs(
                pack_id=pack_id,
                function_id=function_id,
                manifest=manifest or {},
                function_dir=function_dir,
            )
        else:
            raise TypeError(
                "register() requires a FunctionEntry or keyword arguments "
                "(pack_id, function_id, manifest, function_dir)"
            )

        # --- バリデーション ---
        if not resolved_entry.function_id or not resolved_entry.function_id.strip():
            raise ValueError("function_id must not be empty")
        if not resolved_entry.pack_id or not resolved_entry.pack_id.strip():
            raise ValueError("pack_id must not be empty")

        qname = resolved_entry.qualified_name

        with self._lock:
            if qname in self._entries:
                logger.debug(
                    "[FunctionRegistry] Duplicate registration skipped: %s", qname
                )
                return False
            self._entries[qname] = resolved_entry
            self._add_to_tag_index(resolved_entry)
            return True

    def register_pack(
        self, pack_id: str, function_defs: List[Dict[str, Any]]
    ) -> BulkRegisterResult:
        """Pack 内の複数 Function を一括登録する。"""
        if not pack_id or not pack_id.strip():
            raise ValueError("pack_id must not be empty")

        result = BulkRegisterResult()
        for fdef in function_defs:
            try:
                fid = fdef.get("function_id", "")
                entry = FunctionEntry(
                    function_id=fid,
                    pack_id=pack_id,
                    description=fdef.get("description", ""),
                    requires=fdef.get("requires", []),
                    caller_requires=fdef.get("caller_requires", []),
                    host_execution=fdef.get("host_execution", False),
                    tags=fdef.get("tags", []),
                    input_schema=fdef.get("input_schema", {}),
                    output_schema=fdef.get("output_schema", {}),
                    function_dir=fdef.get("function_dir"),
                    main_py_path=fdef.get("main_py_path"),
                    manifest=fdef,
                )
                if self.register(entry):
                    result.registered += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                result.errors.append(f"{fdef.get('function_id', '?')}: {exc}")
                result.skipped += 1

        if result.errors:
            result.success = len(result.errors) == 0
        return result

    # -----------------------------------------------------------------
    # 取得
    # -----------------------------------------------------------------

    def get(self, qualified_name: str) -> Optional[FunctionEntry]:
        """qualified_name (pack_id:function_id) で取得する。"""
        with self._lock:
            return self._entries.get(qualified_name)

    # -----------------------------------------------------------------
    # 一覧
    # -----------------------------------------------------------------

    def list_all(self) -> List[FunctionEntry]:
        with self._lock:
            return list(self._entries.values())

    def list_by_pack(self, pack_id: str) -> List[FunctionEntry]:
        with self._lock:
            return [e for e in self._entries.values() if e.pack_id == pack_id]

    def list_packs(self) -> List[str]:
        with self._lock:
            return sorted({e.pack_id for e in self._entries.values()})

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # -----------------------------------------------------------------
    # 解除
    # -----------------------------------------------------------------

    def unregister_pack(self, pack_id: str) -> int:
        """pack_id に属する全 Function を削除する。削除数を返す。"""
        with self._lock:
            to_remove = [
                qname for qname, e in self._entries.items()
                if e.pack_id == pack_id
            ]
            for qname in to_remove:
                entry = self._entries.pop(qname)
                self._remove_from_tag_index(entry)
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._tag_index.clear()

    # -----------------------------------------------------------------
    # 検索: タグ
    # -----------------------------------------------------------------

    def search_by_tag(self, tags: List[str]) -> List[FunctionEntry]:
        """指定した全タグを持つ Function を返す（AND 検索）。"""
        if not tags:
            return []
        with self._lock:
            normalized = [self._normalize_tag(t) for t in tags]
            sets = []
            for tag in normalized:
                qnames = self._tag_index.get(tag, set())
                sets.append(qnames)
            if not sets:
                return []
            intersection = sets[0]
            for s in sets[1:]:
                intersection = intersection & s
            return [self._entries[qn] for qn in intersection if qn in self._entries]

    # -----------------------------------------------------------------
    # 検索: vocab 同義語
    # -----------------------------------------------------------------

    def search_by_vocab(self, term: str) -> List[FunctionEntry]:
        """
        vocab_registry を使って同義語展開した上で function_id にマッチする
        Function を返す。vocab_registry が None の場合は完全一致のみ。
        """
        with self._lock:
            candidates: set = set()
            if self._vocab_registry is not None:
                try:
                    resolved = self._vocab_registry.resolve(term, to_preferred=True)
                    candidates.add(resolved)
                except Exception:
                    candidates.add(term.strip().lower())
                try:
                    group = self._vocab_registry.get_group(term)
                    if isinstance(group, list):
                        candidates.update(group)
                except Exception:
                    pass
            else:
                candidates.add(term.strip().lower())

            results = []
            for entry in self._entries.values():
                fid = entry.function_id.strip().lower()
                if fid in candidates:
                    results.append(entry)
            return results

    # -----------------------------------------------------------------
    # 検索: ファジー
    # -----------------------------------------------------------------

    def search_fuzzy(
        self, query: str, threshold: float = 0.5
    ) -> List[Tuple[float, FunctionEntry]]:
        """
        function_id と description に対してファジーマッチを行い、
        (score, entry) のリストをスコア降順で返す。
        """
        if not query:
            return []
        with self._lock:
            results: List[Tuple[float, FunctionEntry]] = []
            q = query.strip().lower()
            for entry in self._entries.values():
                fid = entry.function_id.strip().lower()
                desc = entry.description.strip().lower()
                score_fid = difflib.SequenceMatcher(None, q, fid).ratio()
                score_desc = difflib.SequenceMatcher(None, q, desc).ratio()
                best = max(score_fid, score_desc)
                if best >= threshold:
                    results.append((best, entry))
            results.sort(key=lambda x: x[0], reverse=True)
            return results
