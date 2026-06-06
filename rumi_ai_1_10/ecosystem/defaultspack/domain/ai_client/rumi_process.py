from __future__ import annotations

import json
import re
import time
import uuid
from copy import deepcopy
from typing import Any


RUMI_MODEL_PACK_ID = "rumi"
RUMI_MODEL_PACK_REF = "modelpack/rumi"
RUMI_BASE_MODEL = "xiaomi-token-plan-sgp/mimo-v2.5-pro"
RUMI_DISPLAY_NAME = "Rumi"
RUMI_PROCESS_VERSION = "2026-06-04"
RUMI_DEFAULT_THINKING_LEVEL = "medium"
RUMI_BASE_MODEL_CANDIDATES = [
    RUMI_BASE_MODEL,
    "anthropic/claude-sonnet-4-0",
    "openai/gpt-4o",
    "google/gemini-2.5-flash",
]

_ACTION_TOOL_IDS = {
    "todo",
    "web_search",
    "coding_terminal_exec",
    "coding_file_create",
    "coding_file_write",
    "coding_file_patch",
    "coding_git_commit",
    "coding_git_push",
    "browser_use",
    "browser_computer",
    "html_preview",
    "image_render",
}


RUMI_CRITERIA = [
    "Infer the user's background, intent, level, and true goal before drafting.",
    "Treat coding and clearly specified tasks as executable work; keep casual, ambiguous, or advisory tasks more diagnostic.",
    "For large tasks, produce five todo-plan candidates and let a reviewer choose before execution.",
    "Force freshness checks for proper nouns and current facts when search is available; attach source summaries with retrieval time.",
    "Before external actions, state known facts and assumptions; ambiguous phrases such as 'same as last time' are blockers.",
    "Log trace ids for model input/output, tool calls/results, retries, and reviewer decisions so a run can be replayed.",
    "Assume tools can fail with wrong tool, wrong args, partial data, timeout, or permission denied.",
    "Use simple mode for small tasks and deep mode for larger tasks with todo, subtask, review, and watchdog loops.",
    "Escalate on low confidence to search, another AI, a stronger model, or human confirmation.",
    "For UI tasks, render visual artifacts and review screenshots, zoomed regions, spacing, layout, and visual discomfort.",
]


def resolve_rumi_base_model(
    available_models: Any = None,
    *,
    available_providers: Any = None,
) -> str:
    model_ids = {
        str(item or "").strip()
        for item in (available_models if isinstance(available_models, (list, tuple, set)) else [])
        if str(item or "").strip()
    }
    provider_ids = {
        str(item or "").strip()
        for item in (available_providers if isinstance(available_providers, (list, tuple, set)) else [])
        if str(item or "").strip()
    }
    for candidate in RUMI_BASE_MODEL_CANDIDATES:
        if candidate in model_ids:
            return candidate
    for candidate in RUMI_BASE_MODEL_CANDIDATES:
        provider_id, _, _ = candidate.partition("/")
        if provider_id and provider_id in provider_ids:
            return candidate
    return RUMI_BASE_MODEL


def default_rumi_model_pack(*, base_model: str | None = None) -> dict[str, Any]:
    resolved_base_model = str(base_model or RUMI_BASE_MODEL).strip() or RUMI_BASE_MODEL
    return {
        "id": RUMI_MODEL_PACK_ID,
        "display_name": RUMI_DISPLAY_NAME,
        "mode": "review_chain",
        "members": [
            {
                "model": resolved_base_model,
                "label": "Rumi generator",
                "fallback_on": ["rate_limit", "quota", "provider_error", "timeout"],
                "metadata": {
                    "role": "generator",
                    "thinking_level": RUMI_DEFAULT_THINKING_LEVEL,
                    "purpose": "intent, background, explicit reasoning brief, and draft generation",
                },
            },
            {
                "model": resolved_base_model,
                "label": "Rumi reviewer",
                "fallback_on": ["rate_limit", "quota", "provider_error", "timeout"],
                "metadata": {
                    "role": "reviewer",
                    "thinking_level": RUMI_DEFAULT_THINKING_LEVEL,
                    "receives_personalization": False,
                    "purpose": "bias-reduced review of draft, freshness, confidence, tool safety, and process fit",
                },
            },
        ],
        "budget": {
            "simple_max_steps": 1,
            "deep_max_steps": 8,
            "max_review_rounds": 2,
            "max_retries": 2,
            "timeout_seconds": 600,
        },
        "safety": {
            "confidence_threshold": 0.72,
            "quarantine_on_watchdog": True,
            "pre_action_assumption_block_required": True,
            "reviewer_context_excludes_personalization": True,
        },
        "metadata": {
            "builtin": True,
            "process_version": RUMI_PROCESS_VERSION,
            "base_model": resolved_base_model,
            "model_limit_summary": {
                "positioning": "MiMo V2.5 Pro is capable but not a frontier ceiling.",
                "known_stronger_model_classes": ["Claude Sonnet", "Claude Opus", "GPT"],
                "default_behavior": "escalate when confidence or freshness is below threshold",
            },
            "durable_assets": ["workflow", "trace", "eval", "tool_schema", "todo_structure"],
            "tooling": {
                "todo_tool": "todo",
                "search_tool": "web_search",
                "runtime_tools": ["coding_file_create", "coding_terminal_exec", "html_preview", "image_render"],
            },
            "freshness": {
                "proper_nouns_force_search": True,
                "include_retrieved_at": True,
                "reviewer_checks_stale_data": True,
            },
            "review": {
                "reviewer_receives": ["user_input", "draft_answer", "criteria", "freshness_summary"],
                "reviewer_excludes": ["personalization", "private user background hypotheses"],
            },
        },
        "aliases": [RUMI_MODEL_PACK_REF, RUMI_MODEL_PACK_ID],
    }


def ensure_default_rumi_model_pack(model_packs: Any, *, base_model: str | None = None) -> list[dict[str, Any]]:
    packs = [dict(pack) for pack in model_packs if isinstance(pack, dict)] if isinstance(model_packs, list) else []
    materialized = default_rumi_model_pack(base_model=base_model)
    replaced = False
    for index, pack in enumerate(packs):
        pack_id = str(pack.get("id") or "").strip()
        if pack_id != RUMI_MODEL_PACK_ID:
            continue
        metadata = pack.get("metadata") if isinstance(pack.get("metadata"), dict) else {}
        aliases = pack.get("aliases") if isinstance(pack.get("aliases"), list) else []
        if metadata.get("builtin") or RUMI_MODEL_PACK_REF in aliases or RUMI_MODEL_PACK_ID in aliases:
            packs[index] = materialized
        replaced = True
        break
    if not replaced:
        packs.insert(0, materialized)
    return packs


def trace_id() -> str:
    return "rumi-" + uuid.uuid4().hex[:12]


def request_mode(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, params: dict[str, Any] | None = None) -> str:
    raw_mode = str((params or {}).get("rumi_mode") or (params or {}).get("mode") or "").strip().lower()
    if raw_mode in {"simple", "deep"}:
        return raw_mode
    text = messages_text(messages)
    if tools or messages_have_images(messages):
        return "deep"
    if len(text.strip()) <= 160 and not _looks_like_large_task(text):
        return "simple"
    return "deep"


def build_simple_messages(original_messages: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": _simple_system_prompt()},
        {"role": "user", "content": _payload("simple_input", original_messages, context)},
    ]


def build_generator_messages(original_messages: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": _generator_system_prompt()},
        {"role": "user", "content": _payload("deep_input", original_messages, context)},
    ]


def build_review_messages(
    original_messages: list[dict[str, Any]],
    draft: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    review_payload = {
        "phase": "review",
        "user_messages": original_messages,
        "draft_answer": draft,
        "criteria": RUMI_CRITERIA,
        "freshness_summary": context.get("freshness_summary", {}),
        "tool_result_summary": context.get("tool_result_summary", {}),
        "reviewer_context_rule": "Do not use personalization or generated background hypotheses.",
    }
    return [
        {"role": "system", "content": _reviewer_system_prompt()},
        {"role": "user", "content": json.dumps(review_payload, ensure_ascii=False, indent=2)},
    ]


def build_revision_messages(
    original_messages: list[dict[str, Any]],
    previous_draft: str,
    review: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    revision_payload = {
        "phase": "revision",
        "user_messages": original_messages,
        "previous_draft": previous_draft,
        "review": review,
        "criteria": RUMI_CRITERIA,
        "freshness_summary": context.get("freshness_summary", {}),
    }
    return [
        {"role": "system", "content": _revision_system_prompt()},
        {"role": "user", "content": json.dumps(revision_payload, ensure_ascii=False, indent=2)},
    ]


def review_approved(text: str) -> bool:
    lowered = str(text or "").casefold()
    if re.search(r"\bapproved\s*:\s*(yes|true|ok)\b", lowered):
        return True
    if re.search(r"\b(ok|pass)\s*:\s*(yes|true)\b", lowered):
        return True
    if re.search(r"\bapproved\s*:\s*(no|false)\b", lowered):
        return False
    return False


def extract_draft_response(text: str) -> str:
    raw = str(text or "")
    for marker in ("FINAL_RESPONSE:", "DRAFT_RESPONSE:", "ANSWER:"):
        index = raw.find(marker)
        if index >= 0:
            return raw[index + len(marker):].strip()
    return raw.strip()


def messages_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text") or block.get("content") or ""))
    return "\n".join(part for part in parts if part)


def messages_have_images(messages: list[dict[str, Any]]) -> bool:
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").casefold()
            mime = str(block.get("mime_type") or block.get("mime") or "").casefold()
            if block_type in {"image", "image_url", "input_image"} or mime.startswith("image/"):
                return True
    return False


def context_for_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = params if isinstance(params, dict) else {}
    tool_ids = [_tool_id(tool) for tool in (tools or [])]
    tool_ids = [tool_id for tool_id in tool_ids if tool_id]
    text = messages_text(messages)
    return {
        "process_version": RUMI_PROCESS_VERSION,
        "created_at_ms": int(time.time() * 1000),
        "mode": request_mode(messages, tools, params),
        "default_thinking_level": RUMI_DEFAULT_THINKING_LEVEL,
        "available_tool_ids": tool_ids,
        "action_preflight_required": _action_preflight_required(text, tool_ids),
        "freshness_summary": deepcopy(params.get("freshness_summary") if isinstance(params.get("freshness_summary"), dict) else {}),
        "tool_result_summary": deepcopy(params.get("tool_result_summary") if isinstance(params.get("tool_result_summary"), dict) else {}),
        "criteria": list(RUMI_CRITERIA),
    }


def phase_event(phase: str, model: str, *, output: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "id": f"{phase}-{uuid.uuid4().hex[:8]}",
        "phase": phase,
        "model": model,
        "output_chars": len(str(output or "")),
        "output_preview": str(output or "")[:280],
    }
    if metadata:
        event["metadata"] = deepcopy(metadata)
    return event


def response_has_tool_calls(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    if response.get("tool_calls"):
        return True
    choices = response.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else {}
            if isinstance(message, dict) and message.get("tool_calls"):
                return True
    return False


def attach_rumi_metadata(response: Any, process: dict[str, Any]) -> Any:
    if isinstance(response, dict):
        metadata = dict(response.get("metadata") or {})
        metadata["rumi_process"] = deepcopy(process)
        response["metadata"] = metadata
    return response


def _tool_id(tool: dict[str, Any]) -> str:
    if not isinstance(tool, dict):
        return ""
    function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
    return str(tool.get("tool_id") or tool.get("name") or function.get("name") or "").strip()


def _action_preflight_required(text: str, tool_ids: list[str]) -> bool:
    if any(tool_id in _ACTION_TOOL_IDS for tool_id in tool_ids):
        return True
    lowered = str(text or "").casefold()
    return any(token in lowered for token in ("write", "create", "delete", "run", "execute", "commit", "push", "deploy", "open pr"))


def _looks_like_large_task(text: str) -> bool:
    lowered = str(text or "").casefold()
    if len(lowered) > 800:
        return True
    return any(
        token in lowered
        for token in (
            "implement",
            "new pr",
            "pull request",
            "large task",
            "research",
            "design",
            "review loop",
            "todo",
            "architecture",
        )
    )


def _payload(phase: str, original_messages: list[dict[str, Any]], context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "phase": phase,
            "user_messages": original_messages,
            "rumi_context": context,
            "criteria": RUMI_CRITERIA,
        },
        ensure_ascii=False,
        indent=2,
    )


def _simple_system_prompt() -> str:
    return (
        "You are Rumi, a process-centered model built on MiMo V2.5 Pro. "
        "Use a light version of the Rumi process: infer user intent and level, then answer directly. "
        "Do not expose private background speculation unless it helps the user. "
        "If current facts or proper nouns matter and search is available, request freshness before relying on stale memory. "
        "Return only the useful answer unless an action preflight block is required."
    )


def _generator_system_prompt() -> str:
    return (
        "You are Rumi, an improved MiMo V2.5 Pro workflow model. "
        "First produce an explicit concise RUMI_REASONING_BRIEF as model-visible output, not hidden chain-of-thought. "
        "Cover user background hypotheses, intent hypotheses, level fit, proper nouns requiring freshness, simple/deep mode, "
        "confidence, escalation needs, action preflight assumptions, and tool failure risks. "
        "For large tasks, create exactly five todo-plan candidates and choose one only after review. "
        "For UI work, require screenshot/zoom visual evaluation. "
        "Then write DRAFT_RESPONSE with the answer or next action. "
        "Remember MiMo V2.5 Pro is capable but not a frontier ceiling; escalate when the task is risky."
    )


def _reviewer_system_prompt() -> str:
    return (
        "You are the Rumi reviewer. You receive only user input, draft answer, criteria, and freshness/tool summaries. "
        "Do not use personalization or private background hypotheses. "
        "Check intent fit, level fit, latest-information handling, action assumptions, todo quality, tool failure awareness, "
        "confidence/escalation, and whether the answer should be quarantined. "
        "Start with APPROVED: yes or APPROVED: no. Then give concise required fixes."
    )


def _revision_system_prompt() -> str:
    return (
        "You are Rumi revising a draft after reviewer feedback. "
        "Use the feedback to repair the answer while preserving the user's intent. "
        "Return a short RUMI_REASONING_BRIEF if needed, then DRAFT_RESPONSE."
    )
