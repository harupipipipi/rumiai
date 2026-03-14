"""
function_registry.py - Function レジストリ

Pack 内の functions/ ディレクトリに格納された Function を
登録・検索・管理する中央レジストリ。

W24-FIX: Agent A テスト互換 + registry.py _load_functions() 互換
W28-30: multi-runtime support, extensions mechanism
Phase-A: Function unification — FunctionEntry extension

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
# 定数
# =====================================================================

_PROTECTED_VOCAB_PREFIXES: frozenset = frozenset({"system.", "kernel.", "core."})

_VALID_CALLING_CONVENTIONS: frozenset = frozenset({
    "kernel", "subprocess", "block", "python_host",
    "python_docker", "binary", "command",
})


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
    # --- Wave 28: multi-runtime support ---
    runtime: str = "python"          # "python" | "binary" | "command"
    main_binary_path: Any = None     # runtime=binary 用
    command: List[str] = field(default_factory=list)  # runtime=command 用
    docker_image: str = ""           # 空 = デフォルト (python:3.11-slim)
    # --- Wave 30: extensions ---
    extensions: Dict[str, Any] = field(default_factory=dict)
    # --- Phase A: Function unification fields ---
    entrypoint: Optional[str] = None
    risk: Optional[str] = None
    grant_config: Optional[Dict[str, Any]] = None
    vocab_aliases: Optional[List[str]] = None
    # --- Phase A: New fields (shared spec) ---
    permission_id: Optional[str] = None
    handler_py_sha256: Optional[str] = None
    is_builtin: bool = False
    grant_config_schema: Optional[dict] = None
    calling_convention: Optional[str] = None

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
            "runtime": self.runtime,
            "docker_image": self.docker_image,
            "has_extensions": bool(self.extensions),
            "entrypoint": self.entrypoint,
            "risk": self.risk,
            "grant_config": self.grant_config,
            "vocab_aliases": self.vocab_aliases,
            "permission_id": self.permission_id,
            "handler_py_sha256": self.handler_py_sha256,
            "is_builtin": self.is_builtin,
            "grant_config_schema": self.grant_config_schema,
            "calling_convention": self.calling_convention,
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
        self._vocab_alias_map: Dict[str, str] = {}  # alias -> qualified_name
        self._permission_id_index: Dict[str, FunctionEntry] = {}  # permission_id -> entry

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

    def _register_vocab_aliases(self, entry: FunctionEntry) -> None:
        """vocab_aliases を _vocab_alias_map に登録する。保護・重複チェック付き。"""
        if not entry.vocab_aliases:
            return
        qname = entry.qualified_name
        for alias in entry.vocab_aliases:
            # 保護プレフィックスチェック
            is_protected = any(alias.startswith(p) for p in _PROTECTED_VOCAB_PREFIXES)
            if is_protected and not entry.pack_id.startswith("core."):
                logger.warning(
                    "[FunctionRegistry] Protected vocab alias rejected: %s (pack=%s)",
                    alias, entry.pack_id,
                )
                continue
            # 重複チェック
            if alias in self._vocab_alias_map and self._vocab_alias_map[alias] != qname:
                logger.warning(
                    "[FunctionRegistry] Duplicate vocab alias rejected: %s "
                    "(existing=%s, new=%s)",
                    alias, self._vocab_alias_map[alias], qname,
                )
                continue
            self._vocab_alias_map[alias] = qname

    def _unregister_vocab_aliases(self, entry: FunctionEntry) -> None:
        """entry の vocab_aliases を _vocab_alias_map から削除する。"""
        if not entry.vocab_aliases:
            return
        qname = entry.qualified_name
        for alias in entry.vocab_aliases:
            if alias in self._vocab_alias_map and self._vocab_alias_map[alias] == qname:
                del self._vocab_alias_map[alias]

    def _add_to_permission_id_index(self, entry: FunctionEntry) -> None:
        """permission_id が非 None なら _permission_id_index に追加する。"""
        if entry.permission_id is not None:
            self._permission_id_index[entry.permission_id] = entry

    def _remove_from_permission_id_index(self, entry: FunctionEntry) -> None:
        """entry の permission_id を _permission_id_index から削除する。"""
        if entry.permission_id is not None and entry.permission_id in self._permission_id_index:
            if self._permission_id_index[entry.permission_id] is entry:
                del self._permission_id_index[entry.permission_id]

    def _apply_filters(self, entries: List[FunctionEntry], filters: dict) -> List[FunctionEntry]:
        """filters dict に基づいてエントリをフィルタリングする。"""
        result = entries
        if "pack_id" in filters:
            result = [e for e in result if e.pack_id == filters["pack_id"]]
        if "tags" in filters:
            filter_tags = set(filters["tags"])
            result = [e for e in result if filter_tags.issubset(set(e.tags))]
        if "calling_convention" in filters:
            result = [e for e in result if e.calling_convention == filters["calling_convention"]]
        if "is_builtin" in filters:
            result = [e for e in result if e.is_builtin == filters["is_builtin"]]
        if "permission_id" in filters:
            result = [e for e in result if e.permission_id == filters["permission_id"]]
        return result

    @staticmethod
    def _entry_from_kwargs(
        pack_id: str,
        function_id: str,
        manifest: Dict[str, Any],
        function_dir: Any,
    ) -> FunctionEntry:
        """registry.py の _load_functions() が渡すキーワード引数から FunctionEntry を構築する。"""
        m = manifest or {}
        runtime = m.get("runtime", "python")
        main_py = None
        main_binary = None

        if function_dir is not None:
            fd = Path(function_dir)
            if runtime == "python":
                candidate = fd / "main.py"
                if candidate.exists():
                    main_py = candidate
            elif runtime == "binary":
                main_path = m.get("main", "")
                if main_path:
                    candidate = (fd / main_path).resolve()
                    # パストラバーサル防止: function_dir 内に収まっているか検証
                    if candidate.is_relative_to(fd.resolve()) and candidate.exists():
                        main_binary = candidate
                    else:
                        logger.warning(
                            "Binary path escapes function_dir or not found: %s (pack=%s, func=%s)",
                            main_path, pack_id, function_id,
                        )
            # runtime=command の場合は main_py/main_binary は不要

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
            runtime=runtime,
            main_binary_path=main_binary,
            command=m.get("command", []),
            docker_image=m.get("docker_image", ""),
            extensions=m.get("extensions", {}),
            entrypoint=m.get("entrypoint"),
            risk=m.get("risk"),
            grant_config=m.get("grant_config"),
            vocab_aliases=m.get("vocab_aliases"),
            permission_id=m.get("permission_id"),
            handler_py_sha256=m.get("handler_py_sha256"),
            is_builtin=m.get("is_builtin", False),
            grant_config_schema=m.get("grant_config_schema"),
            calling_convention=m.get("calling_convention"),
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
            self._register_vocab_aliases(resolved_entry)
            self._add_to_permission_id_index(resolved_entry)
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

    def register_kernel_function(self, key: str, manifest: dict) -> None:
        """
        manifest dict から FunctionEntry を生成し register() する。

        pack_id = "kernel" 固定
        calling_convention = "kernel" 固定
        is_builtin = True 固定

        Args:
            key: function_id として使用する文字列
            manifest: manifest.json スキーマに準拠した dict
        """
        m = manifest or {}
        entry = FunctionEntry(
            function_id=key,
            pack_id="kernel",
            description=m.get("description", ""),
            requires=m.get("requires", []),
            caller_requires=m.get("caller_requires", []),
            host_execution=m.get("host_execution", False),
            tags=m.get("tags", []),
            input_schema=m.get("input_schema", {}),
            output_schema=m.get("output_schema", {}),
            manifest=m,
            runtime=m.get("runtime", "python"),
            extensions=m.get("extensions", {}),
            entrypoint=m.get("entrypoint"),
            risk=m.get("risk"),
            grant_config=m.get("grant_config"),
            vocab_aliases=m.get("vocab_aliases"),
            permission_id=m.get("permission_id"),
            handler_py_sha256=m.get("handler_py_sha256"),
            is_builtin=True,
            grant_config_schema=m.get("grant_config_schema"),
            calling_convention="kernel",
        )
        self.register(entry)

    # -----------------------------------------------------------------
    # 取得
    # -----------------------------------------------------------------

    def get(self, qualified_name: str) -> Optional[FunctionEntry]:
        """qualified_name (pack_id:function_id) で取得する。"""
        with self._lock:
            return self._entries.get(qualified_name)

    def get_by_permission_id(self, permission_id: str) -> Optional[FunctionEntry]:
        """permission_id から FunctionEntry を O(1) で逆引きする。"""
        with self._lock:
            return self._permission_id_index.get(permission_id)

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
                self._unregister_vocab_aliases(entry)
                self._remove_from_permission_id_index(entry)
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._tag_index.clear()
            self._vocab_alias_map.clear()
            self._permission_id_index.clear()

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

    # -----------------------------------------------------------------
    # 検索: extensions (Wave 30)
    # -----------------------------------------------------------------

    def search_by_extension(self, namespace: str, key: str = None, value: Any = None) -> List[FunctionEntry]:
        """extensions の namespace でフィルタする。"""
        with self._lock:
            results = []
            for entry in self._entries.values():
                ext = entry.extensions.get(namespace)
                if ext is None:
                    continue
                if key is None:
                    results.append(entry)
                elif isinstance(ext, dict) and key in ext:
                    if value is None or ext[key] == value:
                        results.append(entry)
            return results

    # -----------------------------------------------------------------
    # 検索: vocab alias 解決
    # -----------------------------------------------------------------

    def resolve_by_alias(self, alias: str) -> Optional[FunctionEntry]:
        """_vocab_alias_map から alias を解決して FunctionEntry を返す。"""
        with self._lock:
            qname = self._vocab_alias_map.get(alias)
            if qname is None:
                return None
            return self._entries.get(qname)

    # -----------------------------------------------------------------
    # 検索: 統合検索
    # -----------------------------------------------------------------

    def search_unified(
        self,
        query: str = "",
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> List[FunctionEntry]:
        """
        全フィールド横断のテキスト検索 + フィルタリングを行う統合検索。

        query が指定された場合: alias -> tag -> vocab -> fuzzy の順で検索し、
        重複排除して結果をマージする。
        query が空で filters がある場合: 全エントリに対して filters を適用する。
        query が空で filters もない場合: 空リストを返す。

        filters のキー（存在する場合のみ適用）:
            pack_id: 完全一致
            tags: リスト包含（filter の tags が entry の tags のサブセット）
            calling_convention: 完全一致
            is_builtin: 完全一致
            permission_id: 完全一致

        Args:
            query: テキスト検索クエリ
            filters: フィルタリング条件の dict
            limit: 最大返却件数

        Returns:
            マッチした FunctionEntry のリスト
        """
        with self._lock:
            # --- 候補の収集 ---
            if query:
                seen: set = set()
                candidates: List[FunctionEntry] = []

                # 1. resolve_by_alias (完全一致)
                alias_entry = self.resolve_by_alias(query)
                if alias_entry is not None:
                    seen.add(alias_entry.qualified_name)
                    candidates.append(alias_entry)

                # 2. search_by_tag
                tag_entries = self.search_by_tag([query])
                for e in tag_entries:
                    if e.qualified_name not in seen:
                        seen.add(e.qualified_name)
                        candidates.append(e)

                # 3. search_by_vocab
                vocab_entries = self.search_by_vocab(query)
                for e in vocab_entries:
                    if e.qualified_name not in seen:
                        seen.add(e.qualified_name)
                        candidates.append(e)

                # 4. search_fuzzy
                fuzzy_entries = self.search_fuzzy(query)
                for _, e in fuzzy_entries:
                    if e.qualified_name not in seen:
                        seen.add(e.qualified_name)
                        candidates.append(e)
            elif filters:
                # query が空で filters がある場合: 全エントリを候補とする
                candidates = list(self._entries.values())
            else:
                # query が空で filters もない場合
                return []

            # --- フィルタリング ---
            if filters:
                candidates = self._apply_filters(candidates, filters)

            return candidates[:limit]



# =====================================================================
# ManifestRegistry alias (設計決定 D-6)
# =====================================================================

ManifestRegistry = FunctionRegistry
