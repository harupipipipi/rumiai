from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecosystem.defaultspack.domain.templates.tool_policy_merge import (  # noqa: E402
    merge_template_tool_policies,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = (
    ROOT
    / "ecosystem"
    / "defaultspack"
    / "webapp"
    / "src"
    / "lib"
    / "templateToolPolicyMerge.fixtures.json"
)
AUTHORITY_KEYS = {
    "composed_tool_policy_id",
    "template_tool_policy_id",
    "template_tool_policy_ids",
    "template_tool_policy_projected_id",
    "template_tool_policy_projected_ids",
}


def _fixture_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _semantic_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in policy.items() if key not in AUTHORITY_KEYS}


def test_template_tool_policy_merge_shared_fixture_cases():
    for case in _fixture_cases():
        merged = merge_template_tool_policies(
            case.get("policies", []),
            request_disabled_tools=case.get("request_disabled_tools"),
        )
        assert _semantic_policy(merged.policy) == case.get("expected_policy", {}), case["name"]
        assert merged.source_ids == case.get(
            "expected_source_ids",
            sorted(
                {
                    str(item.get("id") or "").strip()
                    for item in case.get("policies", [])
                    if str(item.get("id") or "").strip()
                }
            ),
        ), case["name"]
        if "expected_projected_ids" in case:
            assert merged.projected_ids == case["expected_projected_ids"], case["name"]
        diagnostic_codes = [item.get("code") for item in merged.diagnostics]
        assert diagnostic_codes == case.get("expected_diagnostic_codes", []), case["name"]


def test_template_tool_policy_merge_is_input_order_independent():
    case = {
        "policies": [
            {
                "id": "a",
                "projected_id": "template:a",
                "policy": {
                    "allowed_tools": ["tool_a", "tool_b"],
                    "default_enabled_tools": ["tool_b", "tool_a"],
                },
            },
            {
                "id": "b",
                "projected_id": "template:b",
                "policy": {
                    "allowlist": ["tool_b", "tool_c"],
                    "disabled_tools": ["tool_c"],
                    "params": {"temperature": 0.2},
                },
            },
        ]
    }
    forward = merge_template_tool_policies(case["policies"])
    reverse = merge_template_tool_policies(list(reversed(case["policies"])))
    assert forward.policy == reverse.policy
    assert forward.composed_id == reverse.composed_id
