"""
shared_dict - 共有辞書システム

任意の namespace/token を書き換えできる共有辞書の枠を提供する。
公式は namespace の意味を解釈しない（ecosystem が自由に決める）。

Usage:
    from core_runtime.shared_dict import get_shared_dict_resolver
    
    resolver = get_shared_dict_resolver()
    
    # 解決
    resolved = resolver.resolve("flow_id", "old_name")
    
    # 提案
    result = resolver.propose("flow_id", "old_name", "new_name", provenance={...})
"""

from .resolver import (
    SharedDictResolver,
    get_shared_dict_resolver,
    reset_shared_dict_resolver,
)
from .journal import (
    SharedDictJournal,
    ProposalResult,
    get_shared_dict_journal,
    reset_shared_dict_journal,
)
from .snapshot import (
    SharedDictSnapshot,
    get_shared_dict_snapshot,
    reset_shared_dict_snapshot,
)

__all__ = [
    "SharedDictResolver",
    "get_shared_dict_resolver",
    "reset_shared_dict_resolver",
    "SharedDictJournal",
    "ProposalResult",
    "get_shared_dict_journal",
    "reset_shared_dict_journal",
    "SharedDictSnapshot",
    "get_shared_dict_snapshot",
    "reset_shared_dict_snapshot",
]
