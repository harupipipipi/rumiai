from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..components.registry import DomainComponentRegistry


def _external_component_roots(pack_root: Path) -> list[Path]:
    """Return roots trusted for external webhook profiles and policies.

    External profiles and audience policies are security-sensitive because they
    control webhook authorization and the tools/metadata attached to external
    LLM turns.  Do not use the general component root builder here: it also
    discovers sibling ecosystem packs, including packs that have only been
    applied to disk and have not passed approval/hash verification yet.
    """

    return [
        pack_root / "domain",
        pack_root / "user_data" / "shared" / "domain_components",
    ]


def _registry_for_pack(pack_root: Path) -> DomainComponentRegistry:
    return DomainComponentRegistry(_external_component_roots(pack_root))


def _load_rules(manifest: dict[str, Any]) -> dict[str, Any]:
    entrypoints = manifest.get("entrypoints")
    rules_path = entrypoints.get("rules") if isinstance(entrypoints, dict) else None
    if not isinstance(rules_path, str) or not rules_path.strip():
        rules = manifest.get("rules")
        return deepcopy(rules) if isinstance(rules, dict) else {}
    source_path = manifest.get("source_path")
    if not isinstance(source_path, str) or not source_path:
        return {}
    path = (Path(source_path).parent / rules_path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _profile_specs_from_rules(rules: dict[str, Any]) -> list[dict[str, Any]]:
    profile = rules.get("profile")
    if isinstance(profile, dict):
        return [deepcopy(profile)]
    profiles = rules.get("profiles")
    if isinstance(profiles, list):
        return [deepcopy(item) for item in profiles if isinstance(item, dict)]
    return []


def profile_specs_from_components(pack_root: Path, category: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen_profile_ids: set[str] = set()
    registry = _registry_for_pack(pack_root)
    for component in registry.list(category):
        rules = _load_rules(component.as_dict())
        for spec in _profile_specs_from_rules(rules):
            profile_id = str(spec.get("id") or "").strip()
            if profile_id and profile_id not in seen_profile_ids:
                seen_profile_ids.add(profile_id)
                specs.append(spec)
    return specs


def audience_policy_specs_from_components(pack_root: Path) -> dict[str, dict[str, Any]]:
    policies: dict[str, dict[str, Any]] = {}
    registry = _registry_for_pack(pack_root)
    for component in registry.list("audience_policies"):
        rules = _load_rules(component.as_dict())
        policy = rules.get("policy")
        if not isinstance(policy, dict):
            continue
        policy_id = str(policy.get("id") or component.id).strip()
        if policy_id:
            policies.setdefault(policy_id, deepcopy(policy))
    return policies
