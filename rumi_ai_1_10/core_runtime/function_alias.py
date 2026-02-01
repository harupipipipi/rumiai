"""
function_alias.py - 関数エイリアス（同義語マッピング）システム

@deprecated: vocab_registry.py を使用してください

後方互換のために維持されています。
"""

from __future__ import annotations

import warnings
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class FunctionAliasRegistry:
    """
    関数エイリアスレジストリ
    
    @deprecated: VocabRegistry を使用してください
    """

    _canonical_to_aliases: Dict[str, Set[str]] = field(default_factory=dict)
    _alias_to_canonical: Dict[str, str] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register_aliases(self, canonical: str, aliases: List[str]) -> None:
        with self._lock:
            if canonical in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[canonical]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(canonical)

            if canonical not in self._canonical_to_aliases:
                self._canonical_to_aliases[canonical] = {canonical}

            for alias in aliases:
                if alias in self._alias_to_canonical:
                    old_canonical = self._alias_to_canonical[alias]
                    if old_canonical != canonical:
                        self._canonical_to_aliases[old_canonical].discard(alias)

                self._canonical_to_aliases[canonical].add(alias)
                self._alias_to_canonical[alias] = canonical

            self._alias_to_canonical[canonical] = canonical

    def add_alias(self, canonical: str, alias: str) -> bool:
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                self._canonical_to_aliases[canonical] = {canonical}
                self._alias_to_canonical[canonical] = canonical

            if alias in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[alias]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(alias)

            self._canonical_to_aliases[canonical].add(alias)
            self._alias_to_canonical[alias] = canonical
            return True

    def resolve(self, name: str) -> str:
        with self._lock:
            return self._alias_to_canonical.get(name, name)

    def find_all(self, canonical: str) -> List[str]:
        with self._lock:
            if canonical in self._canonical_to_aliases:
                return sorted(list(self._canonical_to_aliases[canonical]))
            return [canonical]

    def is_alias_of(self, name: str, canonical: str) -> bool:
        with self._lock:
            resolved = self._alias_to_canonical.get(name)
            return resolved == canonical

    def get_canonical(self, name: str) -> Optional[str]:
        with self._lock:
            return self._alias_to_canonical.get(name)

    def list_all_canonicals(self) -> List[str]:
        with self._lock:
            return sorted(list(self._canonical_to_aliases.keys()))

    def list_all_mappings(self) -> Dict[str, List[str]]:
        with self._lock:
            return {
                canonical: sorted(list(aliases))
                for canonical, aliases in self._canonical_to_aliases.items()
            }

    def remove_alias(self, alias: str) -> bool:
        with self._lock:
            if alias not in self._alias_to_canonical:
                return False

            canonical = self._alias_to_canonical[alias]

            if alias == canonical:
                return False

            del self._alias_to_canonical[alias]
            self._canonical_to_aliases[canonical].discard(alias)
            return True

    def remove_canonical(self, canonical: str) -> bool:
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                return False

            for alias in list(self._canonical_to_aliases[canonical]):
                if alias in self._alias_to_canonical:
                    del self._alias_to_canonical[alias]

            del self._canonical_to_aliases[canonical]
            return True

    def clear(self) -> None:
        with self._lock:
            self._canonical_to_aliases.clear()
            self._alias_to_canonical.clear()


_global_function_alias_registry: Optional[FunctionAliasRegistry] = None
_registry_lock = threading.Lock()


def get_function_alias_registry() -> FunctionAliasRegistry:
    """
    @deprecated: get_vocab_registry() を使用してください
    """
    warnings.warn(
        "get_function_alias_registry() is deprecated. Use get_vocab_registry() instead.",
        DeprecationWarning,
        stacklevel=2
    )
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


def get_vocab_registry():
    """vocab_registryを取得（推奨）"""
    from .vocab_registry import get_vocab_registry as _get_vocab
    return _get_vocab()
