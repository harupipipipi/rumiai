from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_registry():
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    return ToolRegistry()


def test_artifact_workspace_priority_and_traversal(tmp_path):
    from domain.artifact.workspace import ArtifactWorkspace

    explicit = tmp_path / "explicit"
    conversation = tmp_path / "conversation"
    workspace = tmp_path / "workspace"

    ws = ArtifactWorkspace(
        {
            "artifact_root": str(explicit),
            "conversation_workspace_dir": str(conversation),
            "workspace_root": str(workspace),
        }
    )
    assert ws.root == explicit.resolve()
    assert ws.resolve("nested/report.md") == (explicit / "nested" / "report.md").resolve()

    fallback = ArtifactWorkspace({"conversation_workspace_dir": str(conversation)})
    assert fallback.root == (conversation / "artifacts").resolve()

    try:
        ws.resolve("../escape.txt")
    except ValueError as exc:
        assert "escapes artifact root" in str(exc)
    else:
        raise AssertionError("path traversal should be rejected")


def test_requested_agent_os_tool_manifests_are_registered():
    from domain.tool.tool_manifest_helpers import REQUESTED_AGENT_OS_TOOL_IDS

    registry = _reset_registry()
    missing = [tool_id for tool_id in REQUESTED_AGENT_OS_TOOL_IDS if registry.get(tool_id) is None]
    assert missing == []

    for tool_id in REQUESTED_AGENT_OS_TOOL_IDS:
        tool = registry.get(tool_id)
        assert tool["trusted"] is True
        assert tool["source_pack_id"] == "defaultspack"
        assert tool["execution"]["handler"].startswith("domain.tool.")
        assert tool["ui"]["widget_kind"] == "tool_toggle"
        assert tool["category"]
        assert tool["action_type"]
        assert tool["risk"] in {"low", "medium", "high"}
        if tool["write_action"] or tool["risk"] == "high":
            assert tool["requires_approval"] is True or tool["risk"] != "high"


def test_artifact_tool_lifecycle_and_preview_export(tmp_path):
    from domain.tool.executor import ToolExecutor

    _reset_registry()
    executor = ToolExecutor()
    context = {"artifact_root": str(tmp_path), "profile_policy": {"yolo_mode": True}}

    write = executor.execute(
        "artifact_file_write",
        {"path": "index.html", "content": "<title>Demo</title><h1>Hello</h1>", "checkpoint": False},
        context,
    )
    assert write["is_error"] is False

    patch = executor.execute(
        "artifact_file_patch",
        {"path": "index.html", "old_text": "Hello", "new_text": "Rumi", "expected_replacements": 1, "checkpoint": False},
        context,
    )
    assert patch["is_error"] is False
    assert "Rumi" in (tmp_path / "index.html").read_text(encoding="utf-8")

    preview = executor.execute("html_preview", {"path": "index.html"}, context)
    assert preview["is_error"] is False
    preview_data = preview["widget"]["data"]
    assert (tmp_path / preview_data["screenshot_path"]).is_file()

    exported = executor.execute("artifact_export", {"path": "index.html", "format": "pdf"}, context)
    assert exported["is_error"] is False
    assert (tmp_path / exported["widget"]["data"]["path"]).is_file()

    listed = executor.execute("artifact_file_list", {"recursive": True}, context)
    paths = {entry["path"] for entry in listed["widget"]["data"]["entries"]}
    assert "index.html" in paths


def test_document_sheet_slides_job_and_workflow_tools(tmp_path):
    from domain.tool.executor import ToolExecutor

    _reset_registry()
    executor = ToolExecutor()
    context = {"artifact_root": str(tmp_path), "profile_policy": {"yolo_mode": True}}

    doc = executor.execute("doc_create", {"title": "Plan", "content": "Body", "output_path": "docs/plan.docx"}, context)
    assert doc["is_error"] is False
    assert (tmp_path / "docs" / "plan.docx").is_file()

    sheet = executor.execute("sheet_create", {"columns": ["name", "score"], "rows": [["a", 1]], "output_path": "data/scores.xlsx"}, context)
    assert sheet["is_error"] is False
    analyzed = executor.execute("sheet_analyze", {"path": "data/scores.xlsx"}, context)
    assert analyzed["widget"]["data"]["row_count"] == 2

    slides = executor.execute(
        "slides_create",
        {"slides": [{"title": "Intro", "bullets": ["One"]}], "output_path": "slides/deck.pptx"},
        context,
    )
    assert slides["is_error"] is False
    assert (tmp_path / "slides" / "deck.pptx").is_file()

    job = executor.execute("job_create", {"kind": "wide_research", "query": "local tools", "input": {"query": "local tools"}}, context)
    assert job["is_error"] is False
    job_id = job["widget"]["data"]["job_id"]
    assert executor.execute("job_status", {"job_id": job_id}, context)["widget"]["data"]["status"] == "completed"

    workflow = executor.execute(
        "workflow_define",
        {"workflow_id": "wf_test", "steps": [{"id": "list", "tool": "artifact_file_list", "args": {"recursive": False}}]},
        context,
    )
    assert workflow["is_error"] is False
    run = executor.execute("workflow_run", {"workflow_id": "wf_test", "approved": True}, context)
    assert run["is_error"] is False
    assert run["widget"]["data"]["status"] == "completed"


def test_xiaomi_token_plan_accepts_all_requested_agent_os_tools(monkeypatch):
    from domain.ai_client.providers.xiaomi_mimo_token_plan_provider import XiaomiMimoTokenPlanSgpProvider
    from domain.tool.schema_adapter import adapt_tool_definitions
    from domain.tool.tool_manifest_helpers import REQUESTED_AGENT_OS_TOOL_IDS

    registry = _reset_registry()
    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token")
    tools = [registry.get(tool_id) for tool_id in REQUESTED_AGENT_OS_TOOL_IDS]
    provider_tools = adapt_tool_definitions(tools)
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(XiaomiMimoTokenPlanSgpProvider, "_request_json", side_effect=fake_request_json):
        response = XiaomiMimoTokenPlanSgpProvider().complete(
            "mimo-v2.5-pro",
            [{"role": "user", "content": "Use the available tools."}],
            provider_tools,
            {"tool_choice": "auto"},
        )

    assert response["content"][0]["text"] == "ok"
    assert captured["path"] == "/chat/completions"
    sent_names = {tool["function"]["name"] for tool in captured["body"]["tools"]}
    assert sent_names == set(REQUESTED_AGENT_OS_TOOL_IDS)
    for tool in captured["body"]["tools"]:
        assert tool["type"] == "function"
        assert tool["function"]["parameters"]["type"] == "object"
