"""
function_alias.py - 関数エイリアス（同義語マッピング）システム

異なる名前で同じ概念を指せるようにし、互換性を高める。

設計原則:
- 公式は具体的なエイリアスをハードコードしない
- ecosystemが自由にエイリアスを追加可能
- 正規名（canonical）と複数のエイリアスをマッピング

Usage:
    alias = get_function_alias_registry()
    
    # エイリアスを登録（ecosystem側で実行）
    alias.register_aliases("ai", ["ai_client", "ai_provider", "llm"])
    alias.register_aliases("tool", ["tools", "function_calling", "tooluse"])
    
    # 解決
    alias.resolve("ai_provider")  # → "ai"
    alias.resolve("unknown")       # → "unknown"（未登録はそのまま）
    
    # 正規名に対応する全ての名前を取得
    alias.find_all("ai")  # → ["ai", "ai_client", "ai_provider", "llm"]
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class FunctionAliasRegistry:
    """
    関数エイリアスレジストリ
    
    正規名（canonical）とエイリアスのマッピングを管理する。
    スレッドセーフ。
    """
    
    # canonical -> set of aliases (canonical自身を含む)
    _canonical_to_aliases: Dict[str, Set[str]] = field(default_factory=dict)
    
    # alias -> canonical
    _alias_to_canonical: Dict[str, str] = field(default_factory=dict)
    
    _lock: threading.RLock = field(default_factory=threading.RLock)
    
    def register_aliases(self, canonical: str, aliases: List[str]) -> None:
        """
        正規名とエイリアスを登録
        
        Args:
            canonical: 正規名（例: "ai", "tool"）
            aliases: エイリアスのリスト（例: ["ai_client", "ai_provider"]）
        
        Note:
            - canonical自身も自動的にエイリアスとして登録される
            - 既に他のcanonicalに登録されているaliasは上書きされる
        """
        with self._lock:
            # canonicalが既存のaliasとして登録されている場合、それを解除
            if canonical in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[canonical]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(canonical)
            
            # canonical自身を含むセットを作成/更新
            if canonical not in self._canonical_to_aliases:
                self._canonical_to_aliases[canonical] = {canonical}
            
            # aliasを登録
            for alias in aliases:
                # 既存の登録を解除
                if alias in self._alias_to_canonical:
                    old_canonical = self._alias_to_canonical[alias]
                    if old_canonical != canonical:
                        self._canonical_to_aliases[old_canonical].discard(alias)
                
                self._canonical_to_aliases[canonical].add(alias)
                self._alias_to_canonical[alias] = canonical
            
            # canonical自身も登録
            self._alias_to_canonical[canonical] = canonical
    
    def add_alias(self, canonical: str, alias: str) -> bool:
        """
        単一のエイリアスを追加
        
        Args:
            canonical: 正規名
            alias: 追加するエイリアス
        
        Returns:
            成功した場合True
        """
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                # canonicalが未登録の場合は新規作成
                self._canonical_to_aliases[canonical] = {canonical}
                self._alias_to_canonical[canonical] = canonical
            
            # 既存の登録を解除
            if alias in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[alias]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(alias)
            
            self._canonical_to_aliases[canonical].add(alias)
            self._alias_to_canonical[alias] = canonical
            return True
    
    def resolve(self, name: str) -> str:
        """
        名前を正規名に解決
        
        Args:
            name: 解決する名前
        
        Returns:
            正規名。未登録の場合はnameをそのまま返す。
        """
        with self._lock:
            return self._alias_to_canonical.get(name, name)
    
    def find_all(self, canonical: str) -> List[str]:
        """
        正規名に対応する全ての名前（エイリアス）を取得
        
        Args:
            canonical: 正規名
        
        Returns:
            canonical自身を含む全てのエイリアスのリスト。
            未登録の場合は[canonical]を返す。
        """
        with self._lock:
            if canonical in self._canonical_to_aliases:
                return sorted(list(self._canonical_to_aliases[canonical]))
            return [canonical]
    
    def is_alias_of(self, name: str, canonical: str) -> bool:
        """
        nameがcanonicalのエイリアスかどうか判定
        
        Args:
            name: 判定する名前
            canonical: 正規名
        
        Returns:
            エイリアスの場合True
        """
        with self._lock:
            resolved = self._alias_to_canonical.get(name)
            return resolved == canonical
    
    def get_canonical(self, name: str) -> Optional[str]:
        """
        名前の正規名を取得（未登録ならNone）
        
        Args:
            name: 名前
        
        Returns:
            正規名、または未登録ならNone
        """
        with self._lock:
            return self._alias_to_canonical.get(name)
    
    def list_all_canonicals(self) -> List[str]:
        """全ての正規名を取得"""
        with self._lock:
            return sorted(list(self._canonical_to_aliases.keys()))
    
    def list_all_mappings(self) -> Dict[str, List[str]]:
        """全てのマッピングを取得"""
        with self._lock:
            return {
                canonical: sorted(list(aliases))
                for canonical, aliases in self._canonical_to_aliases.items()
            }
    
    def remove_alias(self, alias: str) -> bool:
        """
        エイリアスを削除
        
        Args:
            alias: 削除するエイリアス
        
        Returns:
            削除成功した場合True
        
        Note:
            正規名自身は削除できない
        """
        with self._lock:
            if alias not in self._alias_to_canonical:
                return False
            
            canonical = self._alias_to_canonical[alias]
            
            # 正規名自身は削除しない
            if alias == canonical:
                return False
            
            del self._alias_to_canonical[alias]
            self._canonical_to_aliases[canonical].discard(alias)
            return True
    
    def remove_canonical(self, canonical: str) -> bool:
        """
        正規名とその全てのエイリアスを削除
        
        Args:
            canonical: 削除する正規名
        
        Returns:
            削除成功した場合True
        """
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                return False
            
            # 関連する全てのエイリアスを削除
            for alias in list(self._canonical_to_aliases[canonical]):
                if alias in self._alias_to_canonical:
                    del self._alias_to_canonical[alias]
            
            del self._canonical_to_aliases[canonical]
            return True
    
    def clear(self) -> None:
        """全てのマッピングをクリア"""
        with self._lock:
            self._canonical_to_aliases.clear()
            self._alias_to_canonical.clear()


# グローバルインスタンス
_global_function_alias_registry: Optional[FunctionAliasRegistry] = None
_registry_lock = threading.Lock()


def get_function_alias_registry() -> FunctionAliasRegistry:
    """グローバルなFunctionAliasRegistryインスタンスを取得"""
    global _global_function_alias_registry
    if _global_function_alias_registry is None:
        with _registry_lock:
            if _global_function_alias_registry is None:
                _global_function_alias_registry = FunctionAliasRegistry()
    return _global_function_alias_registry


def reset_function_alias_registry() -> FunctionAliasRegistry:
    """FunctionAliasRegistryをリセット（テスト用）"""
    global _global_function_alias_registry
    with _registry_lock:
        _global_function_alias_registry = FunctionAliasRegistry()
    return _global_function_alias_registry
