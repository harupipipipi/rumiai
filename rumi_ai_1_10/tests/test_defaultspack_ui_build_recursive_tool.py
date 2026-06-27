from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.executor import ToolExecutor
from domain.tool.registry import ToolRegistry
from domain.tool.ui_compiler_tools import ui_build_recursive
from ecosystem.defaultspack.transport.registry import canonical_http_route_specs


def test_tool_registry_exposes_recursive_ui_runtime_tools() -> None:
    ToolRegistry._instance = None
    registry = ToolRegistry()

    assert registry.get("tool_ui_build_recursive")["requires_approval"] is True
    assert registry.get("tool_ui_build_recursive")["risk"] == "high"
    for tool_id in [
        "tool_ui_generate_foundation",
        "tool_ui_generate_candidates",
        "tool_ui_render_matrix",
        "tool_ui_inspect_compression",
        "tool_ui_select_candidates",
        "tool_ui_compose_page",
        "tool_ui_verify_recursive_build",
    ]:
        assert registry.get(tool_id)["write_action"] is True


def test_tool_executor_yolo_context_can_run_build_recursive_with_fake_backend(tmp_path: Path) -> None:
    ToolRegistry._instance = None
    write_pass_package(tmp_path / "project")
    result = ToolExecutor().execute(
        "tool_ui_build_recursive",
        build_args("executor-run"),
        {
            "profile_policy": {"yolo_mode": True},
            "conversation_workspace_dir": str(tmp_path),
            "principal_id": "defaultspack",
            "_ui_compiler_backend": "fake",
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "ui_build_recursive"
    assert (tmp_path / ".rumi" / "ui" / "runs" / "executor-run" / "reports" / "final.json").is_file()


def test_raw_yolo_context_cannot_call_runtime_directly(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(
        build_args("raw-runtime"),
        {
            "profile_policy": {"yolo_mode": True},
            "conversation_workspace_dir": str(tmp_path),
            "_ui_compiler_backend": "fake",
        },
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "APPROVAL_REQUIRED"


def test_final_report_contains_all_recursive_build_sections(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("report-run"), fake_context(tmp_path))
    final = json.loads((tmp_path / ".rumi" / "ui" / "runs" / "report-run" / "reports" / "final.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    for key in ["acceptedFoundation", "accepted", "composition", "pageCompression", "verification", "inspections"]:
        assert key in final
    assert final["verification"]["lint"] == "passed"
    assert final["verification"]["test"] == "passed"
    assert final["verification"]["build"] == "passed"


def test_recursive_ui_http_routes_are_registered() -> None:
    routes = {(spec.method, spec.pattern) for spec in canonical_http_route_specs()}

    assert ("POST", "/api/ui/build-recursive") in routes
    assert ("GET", "/api/ui/generation-status") in routes
