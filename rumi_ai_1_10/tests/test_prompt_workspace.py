from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402
from core_runtime.ai_input_trace_store import AiInputTraceStore  # noqa: E402
from domain.prompt.editor import load_prompt_studio, save_prompt, test_prompt_input as run_prompt_studio_test  # noqa: E402
from domain.prompt.usage import (  # noqa: E402
    active_prompt_summary,
    append_runtime_prompt_segment,
    compact_prompt_usage_for_metadata,
    prompt_usage_from_trace,
    toggle_prompt_edge,
)
from transport.registry import _FALLBACK_HTTP_ROUTE_SPECS, prompt_http_route_specs  # noqa: E402


class _EmptyToolRegistry:
    def list_tools(self):
        return []


class _ToolRegistryWithCalculator:
    def list_tools(self):
        return [
            {
                "tool_id": "calculator",
                "name": "calculator",
                "display_name": "Calculator",
                "description": "Evaluate arithmetic expressions.",
                "schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                "metadata": {
                    "source_pack_id": "rumi_default_tools_pack",
                    "skills": ["qa/math-skill"],
                    "skill_triggers": ["calculate", "計算"],
                },
            }
        ]


class _FakePromptManager:
    def get_prompt_by_name(self, prompt_id: str):
        return {
            "id": prompt_id,
            "name": prompt_id,
            "body": "Pack prompt body",
            "content": "Pack prompt body",
            "description": "Read-only pack prompt",
            "variables": [],
            "metadata": {"source": "pack"},
            "read_only": True,
        }

    def get_prompt(self, prompt_id: str):
        return self.get_prompt_by_name(prompt_id)


def _profile(profile_id: str = "prompt-profile") -> dict:
    return {
        "version": 3,
        "profile_id": profile_id,
        "name": "Prompt Profile",
        "base_pack": "defaultspack",
        "graph_id": "defaultspack.startup",
        "packs": ["defaultspack"],
        "metadata": {"selected": {"prompts": ["editable.system", "locked.system"]}},
        "policy": {},
    }


def _setup_profile(monkeypatch, tmp_path: Path, profile: dict | None = None) -> ProfileWorkspaceManager:
    user_data = tmp_path / "user_data"
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data))
    manager = ProfileWorkspaceManager(user_data)
    manager.initialize_profile_workspace(profile or _profile())
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _EmptyToolRegistry)
    return manager


def _fake_effective_prompt(input_data: dict):
    prompt_id = str(input_data.get("system_prompt_id") or "default_chat")
    locked = prompt_id == "locked.system"
    return {
        "prompt_id": prompt_id,
        "source": f"test.{prompt_id}",
        "source_type": "profile_override" if not locked else "pack_default",
        "content": f"Prompt text for {prompt_id}",
        "final_content": f"Prompt text for {prompt_id}",
        "source_chain": [{"source_type": "test", "selected": True, "prompt_id": prompt_id}],
        "metadata": {"allow_disable": not locked},
    }


def test_active_prompt_summary_lists_prompt_context_and_policy_segments(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)

    result = active_prompt_summary(
        {
            "profile_id": "prompt-profile",
            "conversation_id": "chat-1",
            "memory_text": "Remember the user's preferred tone.",
            "include_text": True,
        }
    )

    segments = result["segments"]
    kinds = {segment["kind"] for segment in segments}
    assert result["summary"]["conversation_id"] == "chat-1"
    assert {"profile", "memory"}.issubset(kinds)
    assert any(segment["kind"] == "prompt" or segment["port"] == "policy" for segment in segments)
    assert result["summary"]["token_estimate"]["total"] > 0


def test_active_prompt_summary_explains_tool_schema_boundary(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _ToolRegistryWithCalculator)

    result = active_prompt_summary({"profile_id": "prompt-profile", "include_text": True})
    segment = next(item for item in result["segments"] if item["kind"] == "tool-schema")

    assert segment["prompt_id"] == "calculator"
    assert "Tool schema exposed Calculator" in segment["explanation"]
    assert segment["tool_signal"]["tool_id"] == "calculator"
    assert segment["tool_signal"]["prompt_can_call_tool"] is False
    assert segment["tool_signal"]["skills"] == ["qa/math-skill"]
    assert segment["safety_boundary"]["can_call_tools"] is False
    assert "authority approval" in segment["safety_boundary"]["summary"]


def test_prompt_toggle_uses_disabled_edges_and_respects_allow_disable(monkeypatch, tmp_path: Path) -> None:
    manager = _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    editable_edge = "edge:prompt:editable.system->model_input:default.system"
    locked_edge = "edge:prompt:locked.system->model_input:default.system"

    result = toggle_prompt_edge({"profile_id": "prompt-profile", "edge_id": editable_edge, "enabled": False})
    saved = manager.load_profile_yaml("prompt-profile")

    assert result["enabled"] is False
    assert editable_edge in saved["metadata"]["ai_input"]["disabled_edges"]
    assert any(segment["edge_id"] == editable_edge and segment["status"] == "disabled" for segment in result["summary"]["segments"])
    with pytest.raises(PermissionError):
        toggle_prompt_edge({"profile_id": "prompt-profile", "edge_id": locked_edge, "enabled": False})


def test_runtime_skill_prompt_segment_records_trigger_and_safety_boundary() -> None:
    usage = {"segments": [], "active_segments": [], "disabled_segments": [], "token_estimate": {"total": 0}}
    result = append_runtime_prompt_segment(
        usage,
        {
            "id": "skill:runtime.matched_instructions",
            "prompt_id": "runtime.matched_instructions",
            "label": "Matched skill instructions",
            "kind": "skill",
            "port": "system",
            "source": "RuntimeSkillTriggerService",
            "source_type": "skill",
            "tokens": 12,
            "text": "Use arithmetic format for calculator tasks.",
            "metadata": {
                "matched_skills": [
                    {
                        "id": "qa/math-skill",
                        "display_name": "Math QA",
                        "triggers": ["calculate", "計算"],
                        "applies_to_tools": ["calculator"],
                    }
                ]
            },
        },
    )

    segment = result["segments"][0]
    assert "Runtime skill prompt matched" in segment["explanation"]
    assert segment["skill_signal"]["matched"][0]["id"] == "qa/math-skill"
    assert "calculate" in segment["skill_signal"]["matched"][0]["triggers"]
    assert segment["safety_boundary"]["can_call_tools"] is False
    assert result["active_count"] == 1


def test_prompt_studio_loads_runtime_skill_segments_from_conversation_trace(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    trace = {
        "trace_id": "ait_skill_trace",
        "conversation_id": "chat-skill",
        "run_id": "run-skill",
        "profile_id": "prompt-profile",
        "effective_input": {
            "system_segments": [],
            "developer_segments": [],
            "context_segments": [],
            "tool_schemas": [],
            "policy": {"segments": []},
            "disabled_segments": [],
        },
        "runtime_prompt_segments": [
            {
                "id": "skill:runtime.matched_instructions",
                "prompt_id": "runtime.matched_instructions",
                "label": "Matched skill instructions",
                "kind": "skill",
                "port": "system",
                "source": "RuntimeSkillTriggerService",
                "source_type": "skill",
                "tokens": 8,
                "text": "Skill fired from this message.",
                "metadata": {"matched_skills": [{"id": "qa/math-skill", "triggers": ["計算"], "applies_to_tools": ["calculator"]}]},
            }
        ],
        "token_estimate": {"total": 0},
        "graph": {},
    }
    AiInputTraceStore().save_trace("prompt-profile", trace)

    studio = load_prompt_studio({"profile_id": "prompt-profile", "conversation_id": "chat-skill"})
    segment_records = [
        item for item in studio["prompts"]
        if isinstance(item.get("metadata"), dict) and item["metadata"].get("prompt_usage_segment") is True
    ]

    assert any(item["source_type"] == "skill" and item["prompt_id"] == "runtime.matched_instructions" for item in segment_records)
    assert studio["active_summary"]["segments"][0]["skill_signal"]["matched"][0]["id"] == "qa/math-skill"


def test_prompt_studio_testbench_matches_skill_and_tool_schema(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _ToolRegistryWithCalculator)
    monkeypatch.setattr("domain.tool.registry.ToolRegistry", _ToolRegistryWithCalculator)

    result = run_prompt_studio_test(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "editable.system",
            "draft": "For arithmetic requests, use the calculator tool only after normal tool approval.",
            "user_text": "計算 QA: 12 * 8 を一文で確認して。",
            "selected_tools": ["calculator"],
            "skills": [
                {
                    "id": "qa/math-skill",
                    "display_name": "Math QA",
                    "triggers": ["calculate", "計算"],
                    "applies_to_tools": ["calculator"],
                    "instructions": "Use arithmetic format for calculator tasks.",
                }
            ],
        }
    )

    skill_segment = next(item for item in result["segments"] if item["kind"] == "skill")

    assert result["matched_skills"][0]["id"] == "qa/math-skill"
    assert skill_segment["skill_signal"]["matched"][0]["id"] == "qa/math-skill"
    assert result["selected_tool_segments"][0]["tool_signal"]["tool_id"] == "calculator"
    assert result["prompt_tool_analysis"]["prompt_can_call_tool"] is False
    assert result["safety_boundary"]["can_call_tools"] is False
    assert any(item["id"] == "safety" and item["status"] == "passive" for item in result["verdicts"])


def test_readonly_prompt_save_creates_profile_override(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _FakePromptManager())

    result = save_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "body": "Profile-owned override text",
            "reason": "test_override",
        }
    )

    override_path = Path(result["path"])
    assert result["action"] == "override_saved"
    assert override_path.is_file()
    assert override_path.read_text(encoding="utf-8") == "Profile-owned override text"
    assert "profiles/prompt-profile/prompts/locked.system.system.md" in str(override_path)


def test_prompt_usage_metadata_stores_previews_and_trace_pointer_not_full_text() -> None:
    usage = {
        "trace_id": "trace-1",
        "profile_id": "prompt-profile",
        "conversation_id": "chat-1",
        "run_id": "run-1",
        "active_count": 1,
        "disabled_count": 0,
        "token_estimate": {"total": 3},
        "segments": [
            {
                "id": "prompt:editable.system",
                "status": "active",
                "text": "Visible prompt body",
                "schema": {"type": "object"},
            }
        ],
    }

    compact = compact_prompt_usage_for_metadata(usage)

    assert compact["trace_id"] == "trace-1"
    assert compact["segments"][0]["preview"] == "Visible prompt body"
    assert compact["segments"][0]["has_full_text"] is True
    assert "text" not in compact["segments"][0]
    assert "schema" not in compact["segments"][0]


def test_prompt_trace_detail_can_lazy_load_full_text() -> None:
    trace = {
        "trace_id": "trace-1",
        "profile_id": "prompt-profile",
        "conversation_id": "chat-1",
        "run_id": "run-1",
        "effective_input": {
            "system_segments": [
                {
                    "id": "prompt:editable.system",
                    "text": "Visible prompt body",
                    "metadata": {"prompt_id": "editable.system"},
                }
            ],
            "developer_segments": [],
            "context_segments": [],
            "tool_schemas": [],
            "policy": {"segments": []},
            "disabled_segments": [],
        },
        "graph": {},
        "token_estimate": {"total": 3},
    }

    detail = prompt_usage_from_trace(trace, include_text=True)
    compact = compact_prompt_usage_for_metadata(detail)

    assert detail["segments"][0]["text"] == "Visible prompt body"
    assert "text" not in compact["segments"][0]


def test_prompt_route_specs_have_no_control_stub_and_match_fallback_registry() -> None:
    canonical = {
        (spec.method, spec.pattern, spec.legacy_block_module or spec.block_module or spec.fallback_block_module)
        for spec in prompt_http_route_specs()
    }
    fallback = {
        (spec.method, spec.pattern, spec.legacy_block_module or spec.block_module or spec.fallback_block_module)
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
        if str(spec.pattern).startswith("/api/prompts")
    }

    assert canonical
    assert canonical == fallback
    assert all("/control" not in pattern for _, pattern, _ in canonical)
    assert ("POST", "/api/prompts/editor", "blocks.prompt.control") not in canonical
