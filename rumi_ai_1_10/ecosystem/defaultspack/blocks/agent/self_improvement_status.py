"""defaultspack.self_improvement_status — Self-improvement monitoring endpoint."""

from __future__ import annotations

import sys
from pathlib import Path

_PACK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTSPACK_ROOT = _PACK_ROOT.parent / "defaultspack"
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from blocks._common import ok, error
from domain.agent.self_improvement_runtime import SelfImprovingDefaultspackRuntime


def run(input_data, context=None):
    action = input_data.get("action", "status")
    runtime = _get_runtime(input_data)

    if action == "status":
        return ok(runtime.status())
    if action == "report":
        return ok(runtime.generate_report())
    if action == "pause":
        return ok(runtime.pause())
    if action == "resume":
        return ok(runtime.resume())
    if action == "stop":
        return ok(runtime.stop())
    return error(f"unknown action: {action}", code="INVALID_INPUT")


def _get_runtime(input_data: dict) -> SelfImprovingDefaultspackRuntime:
    from domain.agent.self_improvement_runtime import create_mimo_profile

    profile_id = input_data.get("profile_id", "defaultspack.mimo_coding_company")
    state_path = input_data.get("state_path")
    workspace_root = input_data.get("workspace_root")
    if profile_id == "defaultspack.mimo_coding_company":
        return create_mimo_profile(
            workspace_root=workspace_root,
            state_path=state_path,
        )
    return SelfImprovingDefaultspackRuntime(
        profile_id=profile_id,
        role_map=input_data.get("role_map", {}),
        workspace_root=workspace_root,
        state_path=state_path,
    )
