from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .constants import ACTION_IDS, BUILTIN_PRESET_IDS
from .models import ActionPolicy, PackRecommendation
from .questionnaire import _normalize_preset

PACK_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class PackContractValidation:
    recommendations: list[PackRecommendation] = field(default_factory=list)
    diagnostics: list[dict[str, str]] = field(default_factory=list)


def validate_pack_recommendations(raw: Any) -> PackContractValidation:
    if raw is None:
        return PackContractValidation()
    items = raw if isinstance(raw, list) else [raw]
    recommendations: list[PackRecommendation] = []
    diagnostics: list[dict[str, str]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            diagnostics.append(_diag("pack_contract.item_type", f"recommendation {index} must be an object"))
            continue
        pack_id = str(item.get("pack_id") or item.get("id") or "").strip()
        if not _valid_pack_id(pack_id):
            diagnostics.append(_diag("pack_contract.pack_id", f"invalid pack_id at recommendation {index}"))
            continue
        action_overrides_raw = item.get("action_overrides") or item.get("actions") or {}
        if not isinstance(action_overrides_raw, Mapping):
            diagnostics.append(_diag("pack_contract.actions", f"action_overrides for {pack_id} must be an object"))
            action_overrides_raw = {}
        filtered_actions = {
            action_id: level
            for action_id, level in action_overrides_raw.items()
            if isinstance(action_id, str) and action_id in ACTION_IDS
        }
        action_ceiling = {action_id: "allow" for action_id in ACTION_IDS}
        action_ceiling.update(filtered_actions)
        recommended_preset = item.get("recommended_preset")
        if recommended_preset is not None:
            try:
                recommended_preset = _normalize_preset(recommended_preset)
            except ValueError:
                diagnostics.append(_diag("pack_contract.preset", f"invalid recommended_preset for {pack_id}"))
                recommended_preset = None
        recommendations.append(
            PackRecommendation(
                pack_id=pack_id,
                action_overrides=ActionPolicy.from_mapping(action_ceiling),
                recommended_preset=recommended_preset if recommended_preset in BUILTIN_PRESET_IDS else None,
                reason=str(item.get("reason") or ""),
            )
        )
    return PackContractValidation(recommendations=recommendations, diagnostics=diagnostics)


def _valid_pack_id(pack_id: str) -> bool:
    return bool(PACK_ID_RE.match(pack_id)) and "/" not in pack_id and "\\" not in pack_id and ".." not in pack_id


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": "warning"}
