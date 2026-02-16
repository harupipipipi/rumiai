"""
vocab_registry.py - 語彙統一システム (DI Container 対応)

双方向の同義語解決とデータ変換機能を提供する。

設計原則:
- 公式は「仕組み」のみ提供、具体的な語彙はecosystemが定義
- グループ内の全ての語は同義（双方向解決）
- 変換スクリプトでデータ形式の変換も可能

vocab.txt形式:
    # コメント
    tool, function_calling, tools, tooluse, tool_use
    thinking_budget, reasoning_effort, reasoning_budget

    グループ内の最初の語が「優先語（preferred）」となる。

変換スクリプト:
    converters/{from}_to_{to}.py に convert(data) 関数を定義。
    例: converters/tool_to_function_calling.py

Usage:
    vr = get_vocab_registry()
    
    # 同義語解決
    vr.resolve("function_calling")  # → "tool"（優先語）
    vr.resolve("tool")              # → "tool"（自身が優先語）
    vr.resolve("unknown")           # → "unknown"（未登録はそのまま）
    
    # グループ取得
    vr.get_group("tool")  # → ["tool", "function_calling", "tools", ...]
    
    # 同義判定
    vr.is_synonym("tool", "function_calling")  # → True
    
    # データ変換
    result = vr.convert("tool", "function_calling", {"tools": [...]})
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


MAX_NORMALIZE_DEPTH = 5

VOCAB_FILENAME = "vocab.txt"
CONVERTERS_DIRNAME = "converters"


@dataclass
class VocabGroup:
    """同義語グループ"""
    preferred: str
    members: Set[str]
    source_pack: Optional[str] = None


@dataclass
class ConverterInfo:
    """変換スクリプト情報"""
    from_term: str
    to_term: str
    file_path: Path
    source_pack: Optional[str] = None
    _cached_fn: Optional[Callable] = field(default=None, repr=False)


class VocabRegistry:
    """
    語彙統一レジストリ
    
    双方向の同義語解決とデータ変換を提供する。
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._term_to_group: Dict[str, str] = {}
        self._groups: Dict[str, VocabGroup] = {}
        self._converters: Dict[Tuple[str, str], ConverterInfo] = {}
        self._loaded_packs: Set[str] = set()
        self._group_counter: int = 0
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def register_group(
        self,
        terms: List[str],
        source_pack: Optional[str] = None
    ) -> str:
        """同義語グループを登録"""
        if not terms:
            return ""
        
        terms = [t.strip().lower() for t in terms if t.strip()]
        if not terms:
            return ""
        
        with self._lock:
            preferred = terms[0]
            
            existing_group_ids = set()
            for term in terms:
                if term in self._term_to_group:
                    existing_group_ids.add(self._term_to_group[term])
            
            if existing_group_ids:
                target_group_id = sorted(existing_group_ids, key=lambda x: int(x[1:]))[0]
                target_group = self._groups[target_group_id]
                
                for gid in existing_group_ids:
                    if gid != target_group_id:
                        old_group = self._groups[gid]
                        target_group.members.update(old_group.members)
                        for member in old_group.members:
                            self._term_to_group[member] = target_group_id
                        del self._groups[gid]
                
                for term in terms:
                    target_group.members.add(term)
                    self._term_to_group[term] = target_group_id
                
                return target_group_id
            
            else:
                self._group_counter += 1
                group_id = f"g{self._group_counter}"
                
                group = VocabGroup(
                    preferred=preferred,
                    members=set(terms),
                    source_pack=source_pack
                )
                
                self._groups[group_id] = group
                
                for term in terms:
                    self._term_to_group[term] = group_id
                
                return group_id
    
    def register_synonym(
        self,
        term1: str,
        term2: str,
        source_pack: Optional[str] = None
    ) -> str:
        """2つの語を同義として登録"""
        return self.register_group([term1, term2], source_pack)
    
    def resolve(self, term: str, to_preferred: bool = True) -> str:
        """語を解決"""
        term_lower = term.strip().lower()
        
        with self._lock:
            group_id = self._term_to_group.get(term_lower)
            if group_id is None:
                return term
            
            if to_preferred:
                return self._groups[group_id].preferred
            return term
    
    def resolve_to(self, term: str, target: str) -> str:
        """語を特定のターゲット語に解決"""
        term_lower = term.strip().lower()
        target_lower = target.strip().lower()
        
        with self._lock:
            group_id = self._term_to_group.get(term_lower)
            if group_id is None:
                return term
            
            group = self._groups[group_id]
            if target_lower in group.members:
                return target
            return term
    
    def get_group(self, term: str) -> List[str]:
        """語が属するグループの全メンバーを取得"""
        term_lower = term.strip().lower()
        
        with self._lock:
            group_id = self._term_to_group.get(term_lower)
            if group_id is None:
                return [term]
            
            group = self._groups[group_id]
            members = sorted(group.members)
            if group.preferred in members:
                members.remove(group.preferred)
            return [group.preferred] + members
    
    def is_synonym(self, term1: str, term2: str) -> bool:
        """2つの語が同義かどうか判定"""
        t1 = term1.strip().lower()
        t2 = term2.strip().lower()
        
        if t1 == t2:
            return True
        
        with self._lock:
            g1 = self._term_to_group.get(t1)
            g2 = self._term_to_group.get(t2)
            
            if g1 is None or g2 is None:
                return False
            
            return g1 == g2
    
    def get_preferred(self, term: str) -> str:
        """語の優先語を取得"""
        return self.resolve(term, to_preferred=True)
    
    def register_converter(
        self,
        from_term: str,
        to_term: str,
        file_path: Path,
        source_pack: Optional[str] = None
    ) -> bool:
        """変換スクリプトを登録"""
        if not file_path.exists():
            return False
        
        from_lower = from_term.strip().lower()
        to_lower = to_term.strip().lower()
        
        with self._lock:
            key = (from_lower, to_lower)
            self._converters[key] = ConverterInfo(
                from_term=from_lower,
                to_term=to_lower,
                file_path=file_path,
                source_pack=source_pack
            )
        
        return True
    
    def has_converter(self, from_term: str, to_term: str) -> bool:
        """変換スクリプトが存在するか確認"""
        from_lower = from_term.strip().lower()
        to_lower = to_term.strip().lower()
        
        with self._lock:
            return (from_lower, to_lower) in self._converters
    
    def convert(
        self,
        from_term: str,
        to_term: str,
        data: Any,
        context: Dict[str, Any] = None,
        log_success: bool = False
    ) -> Tuple[Any, bool]:
        """
        データを変換
        
        Args:
            from_term: 変換元の語
            to_term: 変換先の語
            data: 変換するデータ
            context: 変換コンテキスト
            log_success: 成功時も監査ログに記録するか（デフォルトはFalse、ログ過多防止）
        
        Returns:
            (変換後のデータ, 成功したか)
        """
        from_lower = from_term.strip().lower()
        to_lower = to_term.strip().lower()
        
        with self._lock:
            key = (from_lower, to_lower)
            converter_info = self._converters.get(key)
        
        if converter_info is None:
            return data, False
        
        convert_fn = self._get_converter_function(converter_info)
        if convert_fn is None:
            # 変換関数のロード失敗を監査ログに記録
            self._log_conversion(
                from_term=from_term,
                to_term=to_term,
                success=False,
                error="Failed to load converter function",
                converter_info=converter_info
            )
            return data, False
        
        try:
            if context is not None:
                result = convert_fn(data, context)
            else:
                result = convert_fn(data)
            
            # 成功時のログ（オプション）
            if log_success:
                self._log_conversion(
                    from_term=from_term,
                    to_term=to_term,
                    success=True,
                    converter_info=converter_info
                )
            
            return result, True
        except Exception as e:
            # 失敗時は必ず監査ログに記録
            self._log_conversion(
                from_term=from_term,
                to_term=to_term,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                converter_info=converter_info
            )
            print(f"[VocabRegistry] Converter error ({from_term} -> {to_term}): {e}")
            return data, False
    
    def _log_conversion(
        self,
        from_term: str,
        to_term: str,
        success: bool,
        error: str = None,
        error_type: str = None,
        converter_info: ConverterInfo = None
    ) -> None:
        """変換の監査ログを記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            
            details = {
                "from_term": from_term,
                "to_term": to_term,
            }
            
            if converter_info:
                details["converter_file"] = str(converter_info.file_path)
                details["source_pack"] = converter_info.source_pack
            
            if error:
                details["error"] = error
            if error_type:
                details["error_type"] = error_type
            
            audit.log_system_event(
                event_type="vocab_conversion",
                success=success,
                details=details
            )
        except Exception:
            pass  # 監査ログのエラーで処理を止めない
    
    def _get_converter_function(self, info: ConverterInfo) -> Optional[Callable]:
        """変換関数を取得"""
        if info._cached_fn is not None:
            return info._cached_fn
        
        try:
            module_name = f"vocab_converter_{info.from_term}_{info.to_term}_{abs(hash(str(info.file_path)))}"
            spec = importlib.util.spec_from_file_location(module_name, str(info.file_path))
            
            if spec is None or spec.loader is None:
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            fn = getattr(module, "convert", None)
            if fn is None or not callable(fn):
                return None
            
            info._cached_fn = fn
            return fn
        
        except Exception as e:
            print(f"[VocabRegistry] Failed to load converter: {info.file_path}: {e}")
            return None
    
    def load_vocab_file(
        self,
        file_path: Path,
        source_pack: Optional[str] = None
    ) -> int:
        """vocab.txtファイルを読み込み"""
        if not file_path.exists():
            return 0
        
        count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    if not line or line.startswith('#'):
                        continue
                    
                    if ',' in line:
                        terms = [t.strip() for t in line.split(',')]
                    elif '=' in line:
                        terms = [t.strip() for t in line.split('=')]
                    else:
                        continue
                    
                    terms = [t for t in terms if t]
                    if len(terms) >= 2:
                        self.register_group(terms, source_pack)
                        count += 1
        
        except Exception as e:
            print(f"[VocabRegistry] Failed to load vocab file: {file_path}: {e}")
        
        return count
    
    def load_converters_dir(
        self,
        dir_path: Path,
        source_pack: Optional[str] = None
    ) -> int:
        """convertersディレクトリから変換スクリプトを読み込み"""
        if not dir_path.exists() or not dir_path.is_dir():
            return 0
        
        count = 0
        
        for py_file in dir_path.glob("*.py"):
            name = py_file.stem
            
            if "_to_" not in name:
                continue
            
            parts = name.split("_to_", 1)
            if len(parts) != 2:
                continue
            
            from_term, to_term = parts
            
            if self.register_converter(from_term, to_term, py_file, source_pack):
                count += 1
        
        return count
    
    def load_pack_vocab(
        self,
        pack_subdir: Path,
        pack_id: str
    ) -> Dict[str, int]:
        """Packから語彙と変換スクリプトを読み込み"""
        if pack_id in self._loaded_packs:
            return {"groups": 0, "converters": 0}
        
        vocab_file = pack_subdir / VOCAB_FILENAME
        converters_dir = pack_subdir / CONVERTERS_DIRNAME
        
        groups = self.load_vocab_file(vocab_file, pack_id)
        converters = self.load_converters_dir(converters_dir, pack_id)
        
        self._loaded_packs.add(pack_id)
        
        return {"groups": groups, "converters": converters}
    
    def list_groups(self) -> List[Dict[str, Any]]:
        """全グループを取得"""
        with self._lock:
            return [
                {
                    "id": gid,
                    "preferred": g.preferred,
                    "members": sorted(g.members),
                    "source_pack": g.source_pack
                }
                for gid, g in self._groups.items()
            ]
    
    def normalize_dict_keys(
        self,
        data,
        max_depth: int = MAX_NORMALIZE_DEPTH,
        _current_depth: int = 0,
    ):
        """
        dict のキーを優先語（preferred）に正規化する。

        Flow ctx 格納時に呼ばれる。トップレベルおよびネストされた dict の
        キーを vocab グループの preferred term に変換する。

        - ``_`` プレフィックス付きキーは正規化しない（内部制御用）
        - list 内の dict も再帰的に処理する
        - 深さ制限付き（デフォルト MAX_NORMALIZE_DEPTH=5）

        Returns:
            (normalized_data, changes) — changes は
            ``[(original_key, preferred_key), ...]`` のリスト。
            変換が発生しなかった場合は空リスト。
        """
        if not isinstance(data, dict) or _current_depth > max_depth:
            return data, []

        changes = []
        normalized = {}

        with self._lock:
            for key, value in data.items():
                # 内部制御キー（_xxx）はスキップ
                if isinstance(key, str) and key.startswith("_"):
                    new_key = key
                else:
                    new_key = self._resolve_key_unlocked(key)
                    if new_key != key:
                        # 衝突検出: 同じ preferred に複数キーが変換された場合
                        if new_key in normalized:
                            changes.append((f"COLLISION:{key}", new_key))
                        changes.append((key, new_key))

                # ネストされた dict / list 内の dict も再帰処理
                if isinstance(value, dict) and _current_depth < max_depth:
                    value, sub_changes = self.normalize_dict_keys(
                        value, max_depth, _current_depth + 1
                    )
                    changes.extend(sub_changes)
                elif isinstance(value, list) and _current_depth < max_depth:
                    new_list = []
                    for item in value:
                        if isinstance(item, dict):
                            item, sub_changes = self.normalize_dict_keys(
                                item, max_depth, _current_depth + 1
                            )
                            changes.extend(sub_changes)
                        new_list.append(item)
                    value = new_list

                normalized[new_key] = value

        return normalized, changes

    def _resolve_key_unlocked(self, key: str) -> str:
        """ロック取得済みの状態でキーを解決する（内部用）"""
        if not isinstance(key, str):
            return key
        key_lower = key.strip().lower()
        group_id = self._term_to_group.get(key_lower)
        if group_id is None:
            return key
        return self._groups[group_id].preferred

    def list_converters(self) -> List[Dict[str, Any]]:
        """全変換スクリプトを取得"""
        with self._lock:
            return [
                {
                    "from": c.from_term,
                    "to": c.to_term,
                    "file": str(c.file_path),
                    "source_pack": c.source_pack
                }
                for c in self._converters.values()
            ]
    
    def get_registration_summary(self) -> Dict[str, Any]:
        """
        登録状況のサマリーを取得（どのpackがどの語彙を登録したか）
        
        Returns:
            {
                "groups": {pack_id: [groups...]},
                "converters": {pack_id: [converters...]},
                "loaded_packs": [pack_ids...],
                "totals": {"groups": n, "converters": m}
            }
        """
        with self._lock:
            # Pack別にグループを集計
            groups_by_pack: Dict[str, List[Dict[str, Any]]] = {}
            for gid, group in self._groups.items():
                pack_id = group.source_pack or "_unknown"
                if pack_id not in groups_by_pack:
                    groups_by_pack[pack_id] = []
                groups_by_pack[pack_id].append({
                    "id": gid,
                    "preferred": group.preferred,
                    "members": sorted(group.members),
                })
            
            # Pack別にconverterを集計
            converters_by_pack: Dict[str, List[Dict[str, Any]]] = {}
            for converter in self._converters.values():
                pack_id = converter.source_pack or "_unknown"
                if pack_id not in converters_by_pack:
                    converters_by_pack[pack_id] = []
                converters_by_pack[pack_id].append({
                    "from": converter.from_term,
                    "to": converter.to_term,
                    "file": str(converter.file_path),
                })
            
            return {
                "groups_by_pack": groups_by_pack,
                "converters_by_pack": converters_by_pack,
                "loaded_packs": sorted(self._loaded_packs),
                "totals": {
                    "groups": len(self._groups),
                    "converters": len(self._converters),
                    "packs": len(self._loaded_packs),
                }
            }
    
    def clear(self) -> None:
        """全データをクリア"""
        with self._lock:
            self._term_to_group.clear()
            self._groups.clear()
            self._converters.clear()
            self._loaded_packs.clear()
            self._group_counter = 0


def get_vocab_registry() -> VocabRegistry:
    """
    グローバルな VocabRegistry を取得する。

    DI コンテナ経由で遅延初期化・キャッシュされる。

    Returns:
        VocabRegistry インスタンス
    """
    from .di_container import get_container
    return get_container().get("vocab_registry")


def reset_vocab_registry() -> VocabRegistry:
    """
    VocabRegistry をリセットする（テスト用）。

    新しい空の VocabRegistry を生成し、DI コンテナに設定する。

    Returns:
        新しい VocabRegistry インスタンス
    """
    from .di_container import get_container
    new_instance = VocabRegistry()
    get_container().set_instance("vocab_registry", new_instance)
    return new_instance
