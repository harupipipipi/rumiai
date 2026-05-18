from __future__ import annotations

from pathlib import Path

import pytest
import yaml


FLOW_PATH = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack" / "flows" / "chat_turn.flow.yaml"
pytestmark = pytest.mark.contract


def _flow():
    return yaml.safe_load(FLOW_PATH.read_text(encoding="utf-8"))


def test_chat_turn_flow_has_profile_workspace_steps():
    steps = _flow()["steps"]
    ids = [step["id"] for step in steps]
    assert ids[:2] == ["load_active_profile", "load_profile_workspace"]
    functions = {step["id"]: step["function"] for step in steps}
    assert functions["load_active_profile"] == "defaults.profile.load_active"
    assert functions["load_profile_workspace"] == "defaults.profile.workspace"


def test_chat_turn_flow_has_permission_filter_before_call_ai():
    ids = [step["id"] for step in _flow()["steps"]]
    assert ids.index("apply_permissions") < ids.index("route_model") < ids.index("call_ai")


def test_chat_turn_flow_has_persist_and_audit_steps():
    ids = [step["id"] for step in _flow()["steps"]]
    assert "persist_turn" in ids
    assert "audit" in ids
    assert ids.index("persist_turn") < ids.index("audit")
