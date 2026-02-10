"""
hierarchical_grant.py - 階層principalのチェーン解決とconfig統合ヘルパー

principal_id が parent__child__grandchild の形式の場合、
親から順にチェックするためのユーティリティを提供する。
"""

from __future__ import annotations

from typing import Any, Dict, List


PRINCIPAL_SEPARATOR = "__"


def get_principal_chain(principal_id: str) -> List[str]:
    """
    principal_id から親チェーンを生成する。

    例:
        "parent__child__grandchild" ->
        ["parent", "parent__child", "parent__child__grandchild"]
    """
    if not principal_id:
        return []
    parts = principal_id.split(PRINCIPAL_SEPARATOR)
    chain = []
    for i in range(len(parts)):
        chain.append(PRINCIPAL_SEPARATOR.join(parts[: i + 1]))
    return chain


def _intersect_list(parent_value: Any, child_value: Any) -> Any:
    if isinstance(parent_value, (list, tuple, set)) and isinstance(child_value, (list, tuple, set)):
        parent_set = set(parent_value)
        child_set = set(child_value)
        intersection = list(parent_set.intersection(child_set))
        return intersection
    return parent_value


def intersect_configs(parent_config: Dict[str, Any], child_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    parent_config を上限とした config の交差を生成する。

    - parent にないキーは child を採用
    - 両方にあるキーは型に応じて交差
    - parent の制約を優先
    """
    if parent_config is None:
        parent_config = {}
    if child_config is None:
        child_config = {}

    merged: Dict[str, Any] = dict(child_config)

    for key, parent_value in parent_config.items():
        if key not in merged:
            merged[key] = parent_value
            continue

        child_value = merged[key]
        if isinstance(parent_value, dict) and isinstance(child_value, dict):
            merged[key] = intersect_configs(parent_value, child_value)
        elif isinstance(parent_value, (list, tuple, set)) and isinstance(child_value, (list, tuple, set)):
            merged[key] = _intersect_list(parent_value, child_value)
        else:
            merged[key] = parent_value if parent_value != child_value else child_value

    return merged
