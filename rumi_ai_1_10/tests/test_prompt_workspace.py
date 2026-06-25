from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_workspace import ProfileWorkspaceManager, profile_workspace_payload  # noqa: E402
from core_runtime.ai_input_trace_store import AiInputTraceStore  # noqa: E402
from domain.ai_client.tokenizer import count_text_tokens  # noqa: E402
from domain.function_runtime.dispatcher import run_defaultspack_function  # noqa: E402
from domain.prompt.effective import resolve_effective_prompt  # noqa: E402
from domain.prompt.editor import PromptWriteConflict, load_prompt_studio, prompt_versions, rollback_prompt, save_prompt, test_prompt_input as run_prompt_studio_test  # noqa: E402
from domain.prompt.usage import (  # noqa: E402
    active_prompt_summary,
    append_runtime_prompt_segment,
    compact_active_prompt_summary_response,
    compact_prompt_usage_for_metadata,
    get_prompt_trace,
    prompt_usage_from_trace,
    toggle_prompt_edge,
)
from blocks.prompt.active import run as run_prompt_active_block  # noqa: E402
from blocks.prompt.test import run as run_prompt_studio_test_block  # noqa: E402
from transport.registry import _FALLBACK_HTTP_ROUTE_SPECS, prompt_http_route_specs  # noqa: E402


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    def list_prompts(self):
        return [self.get_prompt_by_name("locked.system")]

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


class _EditablePromptManager:
    def __init__(self) -> None:
        self.updated: dict | None = None
        self.prompt = {
            "id": "editable.system",
            "name": "editable.system",
            "body": "Original body",
            "content": "Original body",
            "description": "Keep this description",
            "variables": [{"name": "topic", "type": "string", "required": True}],
            "metadata": {"source": "user_data", "owner": "test"},
            "read_only": False,
        }

    def list_prompts(self):
        return [dict(self.prompt)]

    def get_prompt_by_name(self, prompt_id: str):
        return dict(self.prompt) if prompt_id == "editable.system" else None

    def get_prompt(self, prompt_id: str):
        return self.get_prompt_by_name(prompt_id)

    def update_prompt(self, name: str, updates: dict):
        assert name == "editable.system"
        self.updated = dict(updates)
        self.prompt = {**self.prompt, **updates}
        return dict(self.prompt)


class _EmptyPromptManager:
    def list_prompts(self):
        return []

    def get_prompt_by_name(self, prompt_id: str):
        del prompt_id
        return None

    def get_prompt(self, prompt_id: str):
        del prompt_id
        return None


class _LargePromptManager:
    def __init__(self) -> None:
        self.prompts = [
            {
                "id": f"large.prompt.{index}",
                "name": f"large.prompt.{index}",
                "body": "Large prompt body " + ("x" * 1800),
                "content": "Large prompt body " + ("x" * 1800),
                "description": "Prompt used to exercise compact Studio navigation.",
                "variables": [],
                "metadata": {
                    "source": "pack",
                    "source_pack_id": "large_pack",
                    "path": f"/tmp/large_pack/prompts/large.prompt.{index}.system.md",
                },
                "read_only": True,
            }
            for index in range(90)
        ]

    def list_prompts(self):
        return [dict(prompt) for prompt in self.prompts]

    def get_prompt_by_name(self, prompt_id: str):
        for prompt in self.prompts:
            if prompt["name"] == prompt_id:
                return dict(prompt)
        return None

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
    profile = _profile()
    profile["metadata"]["selected"]["tools"] = ["calculator"]
    profile["metadata"]["selected"]["api_routes"] = ["GET /api/test"]
    manager = _setup_profile(monkeypatch, tmp_path, profile)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    editable_edge = "edge:prompt:editable.system->model_input:default.system"
    locked_edge = "edge:prompt:locked.system->model_input:default.system"

    result = toggle_prompt_edge({"profile_id": "prompt-profile", "edge_id": editable_edge, "enabled": False})
    saved = manager.load_profile_yaml("prompt-profile")

    assert result["enabled"] is False
    assert editable_edge in saved["metadata"]["ai_input"]["disabled_edges"]
    assert "system_prompt_id" not in saved
    assert saved["policy"] == {}
    assert any(segment["edge_id"] == editable_edge and segment["status"] == "disabled" for segment in result["summary"]["segments"])
    with pytest.raises(PermissionError):
        toggle_prompt_edge({"profile_id": "prompt-profile", "edge_id": locked_edge, "enabled": False})


def test_low_risk_prompt_editor_load_cannot_be_promoted_to_save(monkeypatch, tmp_path: Path) -> None:
    manager = _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _FakePromptManager())

    result = run_defaultspack_function(
        "prompt_editor_load",
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "action": "save",
            "body": "This must not be written.",
        },
        {},
    )

    override_path = manager.paths_for_profile("prompt-profile").prompts_dir / "locked.system.system.md"
    assert result["status"] == "ok"
    assert result["data"]["selected_prompt"]["prompt_id"] == "locked.system"
    assert not override_path.exists()


def test_low_risk_prompt_versions_cannot_be_promoted_to_write(monkeypatch, tmp_path: Path) -> None:
    manager = _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _FakePromptManager())
    override_path = manager.paths_for_profile("prompt-profile").prompts_dir / "locked.system.system.md"

    save_result = run_defaultspack_function(
        "prompt_versions",
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "action": "save",
            "body": "This must not be written.",
        },
        {},
    )
    rollback_result = run_defaultspack_function(
        "prompt_versions",
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "action": "rollback",
            "version_id": "missing",
        },
        {},
    )

    assert save_result["status"] == "ok"
    assert rollback_result["status"] == "ok"
    assert save_result["data"]["prompt_id"] == "locked.system"
    assert rollback_result["data"]["prompt_id"] == "locked.system"
    assert not override_path.exists()


def test_low_risk_prompt_preview_toggle_cannot_persist(monkeypatch, tmp_path: Path) -> None:
    manager = _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    editable_edge = "edge:prompt:editable.system->model_input:default.system"

    result = run_defaultspack_function(
        "prompt_preview_toggle",
        {
            "profile_id": "prompt-profile",
            "edge_id": editable_edge,
            "enabled": False,
            "preview": False,
        },
        {},
    )
    saved = manager.load_profile_yaml("prompt-profile")

    assert result["status"] == "ok"
    assert result["data"]["preview"] is True
    assert editable_edge in result["data"]["ai_input"]["disabled_edges"]
    assert saved["metadata"].get("ai_input") is None


def test_prompt_tokenizer_warns_when_model_profile_has_no_tokenizer() -> None:
    result = count_text_tokens(
        "abcdef",
        model_profile_id="proxy/foo",
        profiles=[
            {
                "profile_id": "proxy/foo",
                "provider_id": "proxy",
                "model_id": "foo",
                "same_model_across_providers_key": "foo",
            }
        ],
    )

    assert result["tokens"] > 0
    assert result["tokenizer"]["fallback"] is True
    assert result["tokenizer"]["warning_code"] == "missing_tokenizer"


def test_prompt_tokenizer_borrows_same_model_provider_tokenizer() -> None:
    result = count_text_tokens(
        "abcd",
        model_profile_id="proxy/foo",
        profiles=[
            {
                "profile_id": "proxy/foo",
                "provider_id": "proxy",
                "model_id": "foo",
                "same_model_across_providers_key": "foo",
            },
            {
                "profile_id": "native/foo",
                "provider_id": "native",
                "model_id": "foo",
                "same_model_across_providers_key": "foo",
                "metadata": {
                    "tokenizer": {
                        "kind": "char_divisor",
                        "characters_per_token": 2,
                        "tokenizer_id": "native.foo.test",
                    }
                },
            },
        ],
    )

    assert result["tokens"] == 2
    assert result["tokenizer"]["fallback"] is False
    assert result["tokenizer"]["source"] == "same_model_provider"
    assert result["tokenizer"]["tokenizer_profile_id"] == "native/foo"


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


def test_prompt_studio_load_payload_stays_compact_with_large_tool_catalog(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    body = "Large prompt body " + ("x" * 1800)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _LargePromptManager())
    monkeypatch.setattr(
        "domain.prompt.editor._resolve_effective_prompt_for",
        lambda _profile_id, prompt_id: {
            "prompt_id": prompt_id,
            "source_type": "pack_default",
            "source": "/tmp/large_pack/prompts/large.prompt.0.system.md",
            "content": body,
            "final_content": body,
            "source_chain": [
                {
                    "source_type": "pack_default",
                    "path": "/tmp/large_pack/prompts/large.prompt.0.system.md",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "domain.prompt.editor.active_prompt_summary",
        lambda _data: {
            "summary": {
                "trace_id": "active",
                "profile_id": "prompt-profile",
                "active_count": 2,
                "disabled_count": 0,
                "token_estimate": {
                    "total": 5000,
                    "by_port": {"system": 10, "tools": 4990},
                    "by_node": {"tool_schema:huge": 4990},
                },
                "segments": [
                    {
                        "id": "prompt:large.prompt.0",
                        "prompt_id": "large.prompt.0",
                        "kind": "prompt",
                        "port": "system",
                        "status": "active",
                        "source_type": "pack_default",
                        "tokens": 10,
                        "text": body,
                    },
                    {
                        "id": "tool_schema:huge",
                        "prompt_id": "huge",
                        "kind": "tool-schema",
                        "port": "tools",
                        "status": "active",
                        "source_type": "tool_schema",
                        "tokens": 4990,
                        "schema": {"description": "y" * 120_000},
                    },
                ],
                "active_segments": [],
                "disabled_segments": [],
            },
            "segments": [],
        },
    )

    studio = load_prompt_studio({"profile_id": "prompt-profile", "prompt_id": "large.prompt.0"})
    encoded = json.dumps(studio, ensure_ascii=False).encode("utf-8")

    assert len(encoded) < 65_000
    assert studio["selected_prompt"]["body"] == body
    assert all("body" not in prompt and "content" not in prompt for prompt in studio["prompts"])
    assert all(segment.get("source_type") != "tool_schema" for segment in studio["active_summary"]["segments"])
    assert "by_node" not in studio["active_summary"]["token_estimate"]


def test_prompt_active_block_payload_stays_compact_with_large_tool_catalog(monkeypatch) -> None:
    huge_segment = {
        "id": "tool_schema:huge",
        "edge_id": "edge:tool_schema:huge->model_input:default.tools",
        "prompt_id": "huge",
        "label": "Huge Tool",
        "kind": "tool-schema",
        "port": "tools",
        "status": "active",
        "source": "/tmp/defaultspack/tools/huge/manifest.json",
        "source_type": "tool_schema",
        "source_chain": [{"source_type": "tool_schema", "path": "/tmp/defaultspack/tools/huge/manifest.json", "selected": True}],
        "tokens": 4990,
        "reason": "Tool schema exposed Huge Tool to the model.",
        "allow_disable": True,
        "editable": False,
        "preview": "Huge tool schema preview",
        "metadata": {"schema": "x" * 200_000, "source_chain": [{"path": "/tmp/defaultspack/tools/huge/manifest.json"}]},
        "edge": {"metadata": {"full": "y" * 120_000}},
        "schema": {"description": "z" * 120_000},
    }
    huge_payload = {
        "profile_id": "prompt-profile",
        "conversation_id": "chat-1",
        "summary": {
            "trace_id": "active",
            "profile_id": "prompt-profile",
            "conversation_id": "chat-1",
            "run_id": "active",
            "active_count": 1,
            "disabled_count": 0,
            "token_estimate": {
                "total": 4990,
                "by_port": {"tools": 4990},
                "by_node": {"tool_schema:huge": 4990},
            },
            "segments": [huge_segment],
            "active_segments": [huge_segment],
            "disabled_segments": [],
        },
        "segments": [huge_segment],
        "active_segments": [huge_segment],
        "disabled_segments": [],
        "token_estimate": {"total": 4990, "by_port": {"tools": 4990}, "by_node": {"tool_schema:huge": 4990}},
        "graph": {"nodes": [{"metadata": "n" * 120_000}], "edges": []},
        "ai_input": {"tool_schemas": [{"schema": "s" * 120_000}]},
    }
    monkeypatch.setattr("blocks.prompt.active.active_prompt_summary", lambda _input: huge_payload)

    response = run_prompt_active_block({"profile_id": "prompt-profile"}, {})
    encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
    data = response["data"]

    assert response["status"] == "ok"
    assert len(encoded) < 20_000
    assert "graph" not in data
    assert "ai_input" not in data
    assert "by_node" not in data["summary"]["token_estimate"]
    assert "metadata" not in data["summary"]["segments"][0]
    assert "schema" not in data["summary"]["segments"][0]
    assert data["summary"]["segments"][0]["source"] == "manifest.json"


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
            "model_profile_id": "openai/gpt-5.1",
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
    assert result["model_profile_id"] == "openai/gpt-5.1"
    assert result["input"]["model_profile_id"] == "openai/gpt-5.1"
    assert skill_segment["skill_signal"]["matched"][0]["id"] == "qa/math-skill"
    assert result["selected_tool_segments"][0]["tool_signal"]["tool_id"] == "calculator"
    assert "schema" not in result["selected_tool_segments"][0]
    assert "text" not in result["selected_tool_segments"][0]
    assert all("schema" not in segment and "text" not in segment for segment in result["candidate_tool_segments"])
    assert all(segment["kind"] in {"skill", "context", "memory"} for segment in result["segments"])
    assert result["prompt_tool_analysis"]["prompt_can_call_tool"] is False
    assert result["safety_boundary"]["can_call_tools"] is False
    assert any(item["id"] == "safety" and item["status"] == "passive" for item in result["verdicts"])


def test_prompt_studio_testbench_uses_runtime_skill_registry(monkeypatch, tmp_path: Path) -> None:
    extensions_root = tmp_path / "extensions"
    skill_dir = extensions_root / "skills" / "math-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "qa/math-skill",
                "category": "skill",
                "version": "1",
                "enabled": True,
                "display_name": "Math QA",
                "triggers": ["計算"],
                "applies_to_tools": ["calculator"],
                "instructions": "Use arithmetic format for calculator tasks.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", str(extensions_root))
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_effective_prompt)
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _ToolRegistryWithCalculator)

    response = run_prompt_studio_test_block(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "editable.system",
            "draft": "For arithmetic requests, inspect calculator relevance.",
            "user_text": "計算 QA: 12 * 8 を一文で確認して。",
            "selected_tools": ["calculator"],
            "template_policy": {
                "template_ai_input_ids": ["default_ai_input"],
                "template_tool_policy_ids": ["default_tools"],
            },
        },
        {},
    )
    assert response["status"] == "ok"
    result = response["data"]

    assert result["matched_skills"][0]["id"] == "qa/math-skill"
    assert "arithmetic format" in result["skill_instructions"]
    template_resolution = result["template_tool_policy_resolution"]
    assert template_resolution["applied"] is True
    assert template_resolution["resolved_ai_input_ids"] == ["default_ai_input"]
    assert template_resolution["resolved_template_tool_policy_ids"] == ["default_tools"]
    assert template_resolution["resolved_template_tool_policy_projected_ids"] == [
        "rumi.composer.default:default_tool_policy"
    ]
    assert result["prompt_tool_analysis"]["template_tool_policy"]["applied"] is True
    assert any(
        item["id"] == "template_tool_policy" and item["status"] == "matched"
        for item in result["verdicts"]
    )


def test_readonly_prompt_save_creates_profile_override(monkeypatch, tmp_path: Path) -> None:
    manager = _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _FakePromptManager())

    result = save_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "body": "Profile-owned override text",
            "expected_exists": False,
            "expected_body_hash": _sha256("Pack prompt body"),
            "reason": "test_override",
        }
    )

    override_path = Path(result["path"])
    assert result["action"] == "override_saved"
    assert override_path.is_file()
    assert override_path.read_text(encoding="utf-8") == "Profile-owned override text"
    assert "profiles/prompt-profile/prompts/locked.system.system.md" in str(override_path)

    resolved = resolve_effective_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "workspace": profile_workspace_payload(manager.paths_for_profile("prompt-profile")),
        }
    )
    assert resolved["source_type"] == "profile_override"
    assert resolved["prompt_id"] == "locked.system"
    assert resolved["final_content"] == "Profile-owned override text"


def test_body_only_user_prompt_save_preserves_description_and_variables(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    fake_manager = _EditablePromptManager()
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: fake_manager)
    monkeypatch.setattr("domain.prompt.editor._record_version", lambda **kwargs: {"version_id": "stub"})

    result = save_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "editable.system",
            "body": "Updated body only",
        }
    )

    assert result["action"] == "saved"
    assert fake_manager.updated is not None
    assert fake_manager.updated["description"] == "Keep this description"
    assert fake_manager.updated["variables"] == [{"name": "topic", "type": "string", "required": True}]


def test_stale_user_prompt_save_is_rejected_before_update(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    fake_manager = _EditablePromptManager()
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: fake_manager)

    with pytest.raises(PromptWriteConflict):
        save_prompt(
            {
                "profile_id": "prompt-profile",
                "prompt_id": "editable.system",
                "body": "Stale write",
                "expected_body_hash": _sha256("body from an older tab"),
            }
        )

    assert fake_manager.updated is None
    assert fake_manager.prompt["body"] == "Original body"


def test_first_override_rollback_removes_override_file(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _FakePromptManager())
    saved = save_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "body": "Temporary override",
        }
    )
    override_path = Path(saved["path"])

    result = rollback_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "locked.system",
            "version_id": saved["version"]["version_id"],
        }
    )

    assert result["removed_override"] is True
    assert not override_path.exists()
    versions = prompt_versions({"profile_id": "prompt-profile", "prompt_id": "locked.system"})["versions"]
    assert any(item["reason"] == f"rollback:{saved['version']['version_id']}" for item in versions)
    rollback_version = next(item for item in versions if item["reason"] == f"rollback:{saved['version']['version_id']}")
    assert rollback_version["metadata"]["removed_override"] is True


def test_user_prompt_rollback_records_audit_version(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    fake_manager = _EditablePromptManager()
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: fake_manager)
    monkeypatch.setattr(
        "domain.prompt.editor._version_dir",
        lambda profile_id, prompt_id, scope: tmp_path / "versions" / prompt_id / scope,
    )

    saved = save_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "editable.system",
            "body": "Updated body",
            "expected_body_hash": _sha256("Original body"),
            "reason": "manual_save",
        }
    )
    result = rollback_prompt(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "editable.system",
            "version_id": saved["version"]["version_id"],
            "expected_body_hash": _sha256("Updated body"),
        }
    )

    assert result["action"] == "rolled_back"
    assert fake_manager.prompt["body"] == "Original body"
    versions = prompt_versions({"profile_id": "prompt-profile", "prompt_id": "editable.system"})["versions"]
    assert any(item["reason"] == "manual_save" for item in versions)
    assert any(item["reason"] == f"rollback:{saved['version']['version_id']}" for item in versions)


def test_prompt_studio_uses_profile_snapshot_as_editor_and_test_body(monkeypatch, tmp_path: Path) -> None:
    profile = _profile()
    profile["metadata"]["selected"]["prompts"] = ["snapshot.only"]
    manager = _setup_profile(monkeypatch, tmp_path, profile)
    monkeypatch.setattr("domain.prompt.editor.get_manager", lambda: _EmptyPromptManager())
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _ToolRegistryWithCalculator)
    snapshot_prompt = manager.paths_for_profile("prompt-profile").snapshots_dir / "defaultspack" / "prompts" / "snapshot.only"
    snapshot_prompt.mkdir(parents=True)
    snapshot_body = "Snapshot prompt says to inspect calculator relevance for arithmetic.\n"
    (snapshot_prompt / "prompt.md").write_text(snapshot_body, encoding="utf-8")

    studio = load_prompt_studio({"profile_id": "prompt-profile", "prompt_id": "snapshot.only"})
    selected = studio["selected_prompt"]
    nav_record = next(item for item in studio["prompts"] if item["prompt_id"] == "snapshot.only")

    assert nav_record["source_type"] == "profile_snapshot"
    assert selected["effective_source_type"] == "profile_snapshot"
    assert selected["source_type"] == "profile_snapshot"
    assert selected["read_only"] is True
    assert selected["body"] == snapshot_body
    assert selected["lint"]["estimated_tokens"] > 0

    test_result = run_prompt_studio_test(
        {
            "profile_id": "prompt-profile",
            "prompt_id": "snapshot.only",
            "user_text": "2 + 2 を確認して",
        }
    )

    assert any(item["tool_id"] == "calculator" for item in test_result["tool_candidates"]["from_prompt"])


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


def test_prompt_trace_api_redacts_raw_trace_and_text_by_default(monkeypatch, tmp_path: Path) -> None:
    _setup_profile(monkeypatch, tmp_path)
    trace = {
        "trace_id": "ait_trace_redaction",
        "profile_id": "prompt-profile",
        "conversation_id": "chat-1",
        "run_id": "run-1",
        "effective_input": {
            "system_segments": [
                {
                    "id": "prompt:editable.system",
                    "text": "Sensitive system prompt body",
                    "metadata": {"prompt_id": "editable.system"},
                }
            ],
            "developer_segments": [],
            "context_segments": [
                {"id": "context:user", "text": "Conversation-derived private text"}
            ],
            "tool_schemas": [],
            "policy": {"segments": []},
            "disabled_segments": [],
        },
        "runtime_prompt_segments": [
            {
                "id": "skill:test",
                "source_type": "skill",
                "text": "Runtime skill prompt body",
                "tokens": 4,
            }
        ],
        "provider_payload_summary": {"Authorization": "Bearer secret-token"},
        "graph": {},
        "token_estimate": {"total": 3},
    }
    AiInputTraceStore().save_trace("prompt-profile", trace)

    redacted = get_prompt_trace({"profile_id": "prompt-profile", "trace_id": "ait_trace_redaction"})
    payload_text = json.dumps(redacted, ensure_ascii=False)

    assert redacted is not None
    assert redacted["redaction"]["raw_trace_returned"] is False
    assert redacted["trace"]["effective_input_redacted"] is True
    assert redacted["trace"]["provider_payload_summary"]["Authorization"] == "[REDACTED]"
    assert "effective_input" not in redacted["trace"]
    assert "Sensitive system prompt body" not in payload_text
    assert "Conversation-derived private text" not in payload_text
    assert "Runtime skill prompt body" not in payload_text

    explicit = get_prompt_trace(
        {"profile_id": "prompt-profile", "trace_id": "ait_trace_redaction", "include_text": True}
    )
    assert explicit is not None
    assert explicit["prompt_usage"]["segments"][0]["text"] == "Sensitive system prompt body"


def test_prompt_route_specs_have_no_control_stub_and_match_fallback_registry() -> None:
    prompt_specs = prompt_http_route_specs()
    canonical = {
        (spec.method, spec.pattern, spec.legacy_block_module or spec.block_module or spec.fallback_block_module)
        for spec in prompt_specs
    }
    canonical_sensitive = {(spec.method, spec.pattern): spec.sensitive for spec in prompt_specs}
    fallback = {
        (spec.method, spec.pattern, spec.legacy_block_module or spec.block_module or spec.fallback_block_module)
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
        if str(spec.pattern).startswith("/api/prompts")
    }
    fallback_sensitive = {
        (spec.method, spec.pattern): spec.sensitive
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
        if str(spec.pattern).startswith("/api/prompts")
    }

    assert canonical
    assert canonical == fallback
    assert canonical_sensitive
    assert all(canonical_sensitive.values())
    assert fallback_sensitive == canonical_sensitive
    assert all("/control" not in pattern for _, pattern, _ in canonical)
    assert ("POST", "/api/prompts/editor", "blocks.prompt.control") not in canonical
    assert ("GET", "/api/prompts/editor", "blocks.prompt.editor_load") in canonical
    assert ("POST", "/api/prompts/preview-toggle", "blocks.prompt.preview_toggle") in canonical
    assert ("GET", "/api/prompts/{name}/versions", "blocks.prompt.versions") in canonical
