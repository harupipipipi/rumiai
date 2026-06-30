from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, fixture_tree, write_pass_package

from domain.tool.executor import ToolExecutor
from domain.tool.registry import ToolRegistry
from domain.tool.ui_compiler_tools import ui_build_recursive
from domain.tool.ui_compiler_runtime import run_recursive_build
from domain.tool.ui_compiler_runtime.audit_orchestrator import UIQualityAuditOrchestrator
from domain.tool.ui_compiler_runtime.subagent_backend import SubagentToolBackend
from domain.ui_compiler import RenderMatrix, RenderSnapshot, UIAgentTask
from domain.ui_compiler.planner import RecursiveUIPlanner
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


def test_exported_runtime_helper_does_not_bypass_approval(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = run_recursive_build(
        build_args("raw-helper"),
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
    for key in [
        "intent",
        "foundation",
        "topology",
        "split",
        "candidateGeneration",
        "acceptedSelection",
        "compression",
        "textPressure",
        "typography",
        "colorRoles",
        "surfaceAudit",
        "interactionBudget",
        "responsive",
        "accessibility",
        "qualityAudit",
        "buildTestLint",
        "acceptedFoundation",
        "accepted",
        "composition",
        "pageCompression",
        "verification",
        "inspections",
    ]:
        assert key in final
    assert final["qualityAudit"]["status"] == "pass"
    assert final["verification"]["lint"] == "passed"
    assert final["verification"]["test"] == "passed"
    assert final["verification"]["build"] == "passed"


def test_quality_audit_fails_text_overload_as_first_class_section() -> None:
    plan = RecursiveUIPlanner().plan(fixture_tree(), run_id="audit-overload")
    snapshot = RenderSnapshot(
        subject_id="page",
        candidate_id="composition",
        viewport=390,
        scenario="long",
        text_scale=1,
        image_path="",
        dom_path="",
        console_path="",
        metrics={
            "viewport": 390,
            "visibleTextBlocks": 14,
            "visibleCharacters": 1600,
            "averageLineLength": 108,
            "lineClampCount": 1,
            "ellipsisCount": 3,
            "labelDensity": 3,
            "japaneseBreakQuality": 0.7,
            "visibleActions": 2,
            "allowedActions": 3,
            "mobileDisclosureUsed": True,
            "contrastMin": 4.8,
            "focusVisible": True,
            "keyboardNav": True,
            "ariaRoles": 3,
        },
    )
    foundation = {
        "direction": {"productMode": "utility"},
        "typography": {"roles": {role: {} for role in ["pageTitle", "sectionTitle", "body", "label", "caption", "numeric", "code"]}},
        "spacing": {"density": "compact"},
        "color": {"roles": ["canvas", "surface", "textPrimary", "textSecondary", "actionPrimary", "statusCritical"]},
        "surface": {"maxNestedDepth": 1},
        "primitives": ["Button", "TextInput"],
    }

    audit = UIQualityAuditOrchestrator().audit(
        plan=plan,
        foundation=foundation,
        page_matrix=RenderMatrix(subject_id="page", candidate_id="composition", snapshots=[snapshot]),
        page_compression={"status": "pass", "compressionScore": 0.95, "metrics": {}, "issues": []},
        accepted_count=3,
    )

    assert audit["status"] == "fail"
    assert "textPressure" in audit["failedAudits"]
    assert any("visible character" in issue["message"] for issue in audit["textPressure"]["issues"])


def test_recursive_ui_http_routes_are_registered() -> None:
    routes = {(spec.method, spec.pattern) for spec in canonical_http_route_specs()}

    assert ("POST", "/api/ui/build-recursive") in routes
    assert ("GET", "/api/ui/generation-status") in routes


def test_subagent_tool_backend_runs_real_delegate_path(tmp_path: Path, monkeypatch) -> None:
    from domain.agent import subagent_orchestrator

    def fake_delegate(role_id, payload, *, model="", settings=None, call_handler=None, context=None):
        output_dir = Path(payload["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "result.txt").write_text("delegate wrote output", encoding="utf-8")
        return {"role_id": role_id, "route_kind": "agent.delegate", "model": model}

    monkeypatch.setattr(subagent_orchestrator, "run_subagent_compat", fake_delegate)
    task = UIAgentTask(
        task_id="delegate-task",
        run_id="delegate-run",
        node_id="delegate-node",
        candidate_id="candidate-1",
        kind="leaf",
        prompt="create a component",
        output_dir=str(tmp_path / "candidate"),
        allowed_paths=[str(tmp_path / "candidate")],
    )

    result = SubagentToolBackend().run_task(task, {})

    assert result.ok
    assert result.files == ["result.txt"]
    assert result.metadata["subagent"]["route_kind"] == "agent.delegate"


def test_subagent_compat_forwards_output_contract_to_delegate_params(tmp_path: Path, monkeypatch) -> None:
    from domain.agent.subagent_orchestrator import run_subagent_compat
    from domain.input import dispatcher

    captured = {}

    def fake_dispatch(envelope, context):
        captured["envelope"] = envelope.as_dict()
        captured["context"] = dict(context)
        return {"status": "ok", "delegate": {"status": "completed"}}

    monkeypatch.setattr(dispatcher, "dispatch_input", fake_dispatch)
    output_dir = tmp_path / "candidate"
    result = run_subagent_compat(
        "delegate",
        {
            "task": "create candidate bundle",
            "output_dir": str(output_dir),
            "allowed_paths": [str(output_dir)],
            "metadata": {"nodeId": "reply-composer"},
        },
        context={},
    )

    params = captured["envelope"]["params"]["params"]
    assert result["route_kind"] == "agent.delegate"
    assert params["output_dir"] == str(output_dir)
    assert params["allowed_paths"] == [str(output_dir)]
    assert params["workspace_write_contract"]["mode"] == "create-from-empty-directory"
