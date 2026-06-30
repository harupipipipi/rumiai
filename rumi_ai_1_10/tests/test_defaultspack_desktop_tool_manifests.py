from __future__ import annotations

import json
from pathlib import Path


DEFAULTSPACK_ROOT = Path(__file__).resolve().parent.parent / "ecosystem" / "defaultspack"


def _tool_parameters(tool_id: str) -> dict:
    manifest_path = DEFAULTSPACK_ROOT / "tools" / tool_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest["config"]["schema"]["parameters"]


def test_desktop_operator_skill_applies_to_every_desktop_tool() -> None:
    manifest_path = DEFAULTSPACK_ROOT / "extensions" / "skills" / "desktop_operator" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    desktop_tool_ids = {
        path.name
        for path in (DEFAULTSPACK_ROOT / "tools").iterdir()
        if path.is_dir() and path.name.startswith("desktop_")
    }

    assert desktop_tool_ids
    assert desktop_tool_ids <= set(manifest["applies_to_tools"])


def test_desktop_create_manifest_exposes_runtime_context_fields() -> None:
    parameters = _tool_parameters("desktop_create")
    properties = parameters["properties"]

    for field in [
        "starter",
        "browser_url",
        "workspace_id",
        "workspace_access",
        "assigned_agent",
        "assigned_agent_id",
        "access_request_required",
        "provisioning",
    ]:
        assert field in properties

    assert set(properties["starter"]["enum"]) == {"empty", "browser", "terminal", "browser_url"}
    assert set(properties["workspace_access"]["enum"]) == {"none", "read_only", "overlay", None}

    access = properties["access"]["properties"]
    assert "request_required" in access["mode"]["enum"]
    assert access["request_required"]["type"] == "boolean"
    assert properties["provisioning"]["properties"]["mcp_servers"]["items"]["type"] == "string"


def test_desktop_rules_manifest_exposes_request_required_access() -> None:
    properties = _tool_parameters("desktop_rules_update")["properties"]
    access = properties["access"]["properties"]

    assert "request_required" in access["mode"]["enum"]
    assert access["request_required"]["type"] == "boolean"
    assert properties["access_request_required"]["type"] == "boolean"


def test_desktop_access_manifests_expose_request_and_grant_identity() -> None:
    request_properties = _tool_parameters("desktop_access_request")["properties"]
    grant_parameters = _tool_parameters("desktop_access_grant")

    assert {"seat_id", "desktop_id", "requester_id", "owner_id", "reason"}.issubset(request_properties)
    assert grant_parameters["required"] == ["request_id"]
    assert {"seat_id"} in [set(item["required"]) for item in grant_parameters["anyOf"]]
    assert {"desktop_id"} in [set(item["required"]) for item in grant_parameters["anyOf"]]
