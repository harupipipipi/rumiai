"""
dependency_resolver.py - Pack 依存関係解決

トポロジカルソート（Kahn's algorithm）で Pack のロード順序を決定する。
循環依存を検出してエラー（またはソフトフェイル）にする。

Wave 31: registry.py の 3 ソース統合ロジックを取り込み汎用化。
  - extract_dependencies(): pack-level の明示的依存を 3 ソースから抽出
  - resolve_load_order(): heapq ベース安定ソート + soft_circular モード追加
  - validate_dependencies(): 依存関係を検証しレポートを返す

Usage:
    from core_runtime.dependency_resolver import resolve_load_order

    packs = {
        "pack_a": {"depends_on": [{"pack_id": "pack_b"}]},
        "pack_b": {"dependencies": {"pack_c": {}}},
        "pack_c": {},
    }
    order = resolve_load_order(packs)
    # => ["pack_c", "pack_b", "pack_a"]
"""

from __future__ import annotations

import heapq
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception classes (interface unchanged)
# ---------------------------------------------------------------------------

class DependencyError(Exception):
    """依存関係エラー"""
    pass


class CircularDependencyError(DependencyError):
    """循環依存エラー"""
    pass


class MissingDependencyError(DependencyError):
    """依存先が見つからない"""
    pass


# ---------------------------------------------------------------------------
# extract_dependencies — pack-level 3 source extraction
# ---------------------------------------------------------------------------

def extract_dependencies(pack_info: Dict[str, Any]) -> List[str]:
    """
    単一 pack の manifest / ecosystem dict から依存 pack_id を抽出する。

    3 つのソースを統合し、重複を排除してユニークなリストで返す。

    Sources:
        1. ``depends_on`` — 明示的依存。
           - list の場合: 要素が dict なら ``dep["pack_id"]``、str ならそのまま。
           - dict の場合: キーを pack_id として扱う。
        2. ``dependencies`` — ecosystem.json の dependencies フィールド。
           - dict の場合: キーを pack_id として扱う。
           - list の場合: 要素をそのまま pack_id として扱う。
        3. ``connectivity.requires`` — pack レベルの connectivity.requires。
           - list の場合: 要素をそのまま pack_id として扱う。

    Args:
        pack_info: pack の manifest / ecosystem dict

    Returns:
        依存 pack_id のユニークなリスト（出現順保持）
    """
    seen: set = set()
    result: List[str] = []

    def _add(pid: str) -> None:
        if pid and pid not in seen:
            seen.add(pid)
            result.append(pid)

    # --- Source 1: depends_on ---
    raw_depends_on = pack_info.get("depends_on")
    if isinstance(raw_depends_on, list):
        for dep in raw_depends_on:
            if isinstance(dep, dict):
                pid = dep.get("pack_id", "")
                _add(str(pid) if pid else "")
            elif isinstance(dep, str):
                _add(dep)
    elif isinstance(raw_depends_on, dict):
        for pid in raw_depends_on:
            _add(str(pid))

    # --- Source 2: dependencies ---
    raw_dependencies = pack_info.get("dependencies")
    if isinstance(raw_dependencies, dict):
        for pid in raw_dependencies:
            _add(str(pid))
    elif isinstance(raw_dependencies, list):
        for pid in raw_dependencies:
            if isinstance(pid, str):
                _add(pid)

    # --- Source 3: connectivity.requires ---
    raw_conn = pack_info.get("connectivity")
    if isinstance(raw_conn, dict):
        raw_requires = raw_conn.get("requires")
        if isinstance(raw_requires, list):
            for pid in raw_requires:
                if isinstance(pid, str):
                    _add(pid)

    return result


# ---------------------------------------------------------------------------
# _build_type_to_packs — component-level provides mapping
# ---------------------------------------------------------------------------

def _build_type_to_packs(packs: Dict[str, Dict[str, Any]]) -> Dict[str, set]:
    """
    全 pack の components から type → provider pack_id のマップを構築する。

    pack dict 内の ``components`` は ``{key: component_dict}`` 形式を想定。
    各 component_dict に ``connectivity.provides`` (list[str]) があればマッピングする。
    """
    type_to_packs: Dict[str, set] = {}
    for pack_id, manifest in packs.items():
        raw_components = manifest.get("components")
        if not isinstance(raw_components, dict):
            continue
        for _comp_key, comp_data in raw_components.items():
            if not isinstance(comp_data, dict):
                continue
            comp_conn = comp_data.get("connectivity")
            if not isinstance(comp_conn, dict):
                continue
            provides = comp_conn.get("provides")
            if isinstance(provides, list):
                for ptype in provides:
                    if isinstance(ptype, str) and ptype:
                        if ptype not in type_to_packs:
                            type_to_packs[ptype] = set()
                        type_to_packs[ptype].add(pack_id)
    return type_to_packs


def _collect_component_requires(
    pack_id: str,
    manifest: Dict[str, Any],
    type_to_packs: Dict[str, set],
) -> set:
    """
    pack 内の各 component の connectivity.requires から
    type_to_packs 経由で依存 pack_id を収集する。
    """
    deps: set = set()
    raw_components = manifest.get("components")
    if not isinstance(raw_components, dict):
        return deps
    for _comp_key, comp_data in raw_components.items():
        if not isinstance(comp_data, dict):
            continue
        comp_conn = comp_data.get("connectivity")
        if not isinstance(comp_conn, dict):
            continue
        requires = comp_conn.get("requires")
        if isinstance(requires, list):
            for req_type in requires:
                provider_packs = type_to_packs.get(req_type, set())
                for provider_id in provider_packs:
                    if provider_id != pack_id:
                        deps.add(provider_id)
    return deps


# ---------------------------------------------------------------------------
# resolve_load_order
# ---------------------------------------------------------------------------

def resolve_load_order(
    packs: Dict[str, Dict[str, Any]],
    strict: bool = False,
    soft_circular: bool = False,
) -> List[str]:
    """
    Pack の依存関係をトポロジカルソートで解決し、ロード順序を返す。

    依存関係ソース:
        1. ``depends_on`` — 明示的依存（リスト / dict）
        2. ``dependencies`` — ecosystem.json の dependencies
        3. ``connectivity.requires`` — pack レベル
        4. component-level ``connectivity.requires`` → type_to_packs 解決

    Args:
        packs: ``{pack_id: pack_manifest}`` の辞書。
        strict: True なら依存先不在で MissingDependencyError を raise。
                False なら warning ログしてスキップ。
        soft_circular: True なら循環検出時にエラーログ + アルファベット順で末尾追加。
                       False (デフォルト) なら CircularDependencyError を raise。

    Returns:
        ロード順の pack_id リスト

    Raises:
        CircularDependencyError: soft_circular=False で循環依存がある場合
        MissingDependencyError: strict=True で依存先がない場合
    """
    all_pack_ids = set(packs.keys())
    if not all_pack_ids:
        return []

    # component-level provides → type_to_packs mapping
    type_to_packs = _build_type_to_packs(packs)

    # 隣接リスト構築（dep → dependants）
    graph: Dict[str, List[str]] = {pid: [] for pid in all_pack_ids}
    in_degree: Dict[str, int] = {pid: 0 for pid in all_pack_ids}

    for pid, manifest in packs.items():
        # pack-level dependencies (3 sources)
        deps: set = set(extract_dependencies(manifest))

        # component-level requires → type_to_packs resolution
        comp_deps = _collect_component_requires(pid, manifest, type_to_packs)
        deps.update(comp_deps)

        # 自己依存を除外
        deps.discard(pid)

        for dep_id in deps:
            if dep_id not in all_pack_ids:
                if strict:
                    raise MissingDependencyError(
                        "Pack '{}' depends on '{}' which is not installed".format(
                            pid, dep_id
                        )
                    )
                logger.warning(
                    "Pack '%s' depends on '%s' which is not installed (skipping dependency)",
                    pid,
                    dep_id,
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

    if len(result) != len(all_pack_ids):
        remaining = sorted(all_pack_ids - set(result))
        if soft_circular:
            logger.error(
                "Circular dependency detected among packs: %s  "
                "Loading cyclic packs in alphabetical order at end of load_order.",
                remaining,
            )
            result.extend(remaining)
        else:
            raise CircularDependencyError(
                "Circular dependency detected among: {{{}}}".format(
                    ", ".join("'{}'".format(p) for p in remaining)
                )
            )

    return result


# ---------------------------------------------------------------------------
# validate_dependencies
# ---------------------------------------------------------------------------

def validate_dependencies(
    packs: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    全 pack の依存関係を検証し、問題のリストを返す。

    検出する問題:
        - missing: 依存先が packs に存在しない
        - self_dependency: 自分自身に依存している
        - circular: 循環依存が存在する

    Args:
        packs: ``{pack_id: pack_manifest}`` の辞書

    Returns:
        問題のリスト。問題がなければ空リスト。
        各要素は dict で、``type`` キーに問題種別を持つ:
            - ``{"type": "missing", "pack_id": ..., "depends_on": ...}``
            - ``{"type": "self_dependency", "pack_id": ...}``
            - ``{"type": "circular", "packs": [...]}``
    """
    issues: List[Dict[str, Any]] = []
    all_pack_ids = set(packs.keys())

    # component-level provides → type_to_packs mapping
    type_to_packs = _build_type_to_packs(packs)

    # 隣接リスト（循環検出用）
    graph: Dict[str, List[str]] = {pid: [] for pid in all_pack_ids}
    in_degree: Dict[str, int] = {pid: 0 for pid in all_pack_ids}

    for pid, manifest in packs.items():
        deps: set = set(extract_dependencies(manifest))
        comp_deps = _collect_component_requires(pid, manifest, type_to_packs)
        deps.update(comp_deps)

        # self_dependency check
        if pid in deps:
            issues.append({"type": "self_dependency", "pack_id": pid})
            deps.discard(pid)

        for dep_id in deps:
            if dep_id not in all_pack_ids:
                issues.append({
                    "type": "missing",
                    "pack_id": pid,
                    "depends_on": dep_id,
                })
                continue
            graph[dep_id].append(pid)
            in_degree[pid] += 1

    # Kahn's algorithm for circular detection
    heap = sorted(pid for pid, deg in in_degree.items() if deg == 0)
    heapq.heapify(heap)
    visited: List[str] = []

    while heap:
        pid = heapq.heappop(heap)
        visited.append(pid)
        for neighbor in graph.get(pid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)

    if len(visited) != len(all_pack_ids):
        remaining = sorted(all_pack_ids - set(visited))
        issues.append({"type": "circular", "packs": remaining})

    return issues


# --- バージョン制約（将来対応 TODO） ---
# depends_on に {"pack_id": "xxx", "version": ">=1.0.0"} がある場合、
# バージョン比較を行う関数をここに追加する。
# 現在は存在チェックのみ。
# Phase 2 で registry.py が dependency_resolver.py を呼ぶようにリファクタする際に
# バージョン制約対応も検討する。
