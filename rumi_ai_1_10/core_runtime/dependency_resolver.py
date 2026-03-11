"""
dependency_resolver.py - Pack 依存関係解決

トポロジカルソート（Kahn's algorithm）で Pack のロード順序を決定する。
循環依存を検出してエラーにする。

Usage:
    from core_runtime.dependency_resolver import resolve_load_order

    packs = {
        "pack_a": {"depends_on": [{"pack_id": "pack_b"}]},
        "pack_b": {},
        "pack_c": {"depends_on": [{"pack_id": "pack_a"}]},
    }
    order = resolve_load_order(packs)
    # => ["pack_b", "pack_a", "pack_c"]
"""

from __future__ import annotations

import heapq
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """依存関係エラー"""
    pass


class CircularDependencyError(DependencyError):
    """循環依存エラー"""
    pass


class MissingDependencyError(DependencyError):
    """依存先が見つからない"""
    pass


def resolve_load_order(
    packs: Dict[str, Dict[str, Any]],
    strict: bool = False,
) -> List[str]:
    """
    Pack の依存関係をトポロジカルソートで解決し、ロード順序を返す。

    Args:
        packs: {pack_id: pack_manifest} の辞書。
               各 manifest は "depends_on" キーを持つ。
               depends_on の要素は {"pack_id": "xxx"} または文字列。
               バージョン制約は将来対応（現在は存在チェックのみ）。
        strict: True なら依存先不在でエラー、False なら警告してスキップ

    Returns:
        ロード順の pack_id リスト

    Raises:
        CircularDependencyError: 循環依存がある場合
        MissingDependencyError: strict=True で依存先がない場合
    """
    # 隣接リスト構築（dep → dependant）
    graph: Dict[str, List[str]] = {pid: [] for pid in packs}
    in_degree: Dict[str, int] = {pid: 0 for pid in packs}

    for pid, manifest in packs.items():
        deps = manifest.get("depends_on", [])
        if not isinstance(deps, list):
            deps = [deps]
        for dep in deps:
            dep_id = dep["pack_id"] if isinstance(dep, dict) else str(dep)
            if dep_id not in packs:
                if strict:
                    raise MissingDependencyError(
                        f"Pack '{pid}' depends on '{dep_id}' which is not installed"
                    )
                logger.warning(
                    "Pack '%s' depends on '%s' which is not installed (skipping dependency)",
                    pid, dep_id,
                )
                continue
            graph[dep_id].append(pid)
            in_degree[pid] += 1

    # Kahn's algorithm with heapq for stable ordering
    heap = sorted(pid for pid, deg in in_degree.items() if deg == 0)
    heapq.heapify(heap)
    result: List[str] = []

    while heap:
        pid = heapq.heappop(heap)
        result.append(pid)
        for neighbor in graph.get(pid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)

    if len(result) != len(packs):
        remaining = set(packs.keys()) - set(result)
        raise CircularDependencyError(
            f"Circular dependency detected among: {remaining}"
        )

    return result


# --- バージョン制約（将来対応 TODO） ---
# depends_on に {"pack_id": "xxx", "version": ">=1.0.0"} がある場合、
# バージョン比較を行う関数をここに追加する。
# 現在は存在チェックのみ。
