import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.agent_runtime.context_snapshot import build_run_context_snapshot
from domain.context_engine.compact_packet import build_compact_packet
from domain.context_engine.validation import validate_compact_packet
from domain.hooks.dispatcher import dispatch_hook


def _pack_root():
    return Path(__file__).resolve().parents[2]


def _context_root():
    root = _pack_root() / "user_data" / "context"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bool_value(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _merge_run_snapshot(input_data, context=None):
    if not _bool_value(input_data.get("include_run_snapshot")):
        return input_data
    run_id = str(input_data.get("run_id") or "").strip()
    if not run_id:
        return input_data
    snapshot = build_run_context_snapshot(
        run_id,
        context=context if isinstance(context, dict) else {},
        require_context_match=True,
    )
    merged = dict(input_data)
    for key in (
        "progress",
        "changed_files",
        "tool_results",
        "terminal_results",
        "critical_context",
        "next_steps",
    ):
        if not merged.get(key) and snapshot.get(key):
            merged[key] = snapshot[key]
    return merged


def run(input_data, context=None):
    context = context or {}
    input_data = _merge_run_snapshot(input_data or {}, context)
    dispatch_hook("before_compaction", {"input": input_data, "context": context or {}})
    summary = input_data.get("summary")
    if summary is None:
        messages = input_data.get("messages", [])
        if isinstance(messages, list):
            lines = []
            for message in messages[-20:]:
                if isinstance(message, dict):
                    lines.append(str(message.get("role", "unknown")) + ": " + str(message.get("content", ""))[:500])
            summary = "\n".join(lines)
        else:
            summary = ""
    payload = build_compact_packet(
        run_id=str(input_data.get("run_id", "")),
        conversation_id=str(input_data.get("conversation_id", "")),
        goal=str(input_data.get("goal", "")),
        summary=str(summary),
        source_transcript_id=str(input_data.get("source_transcript_id", "")),
        replacement_transcript_id=str(input_data.get("replacement_transcript_id", "")),
        progress=input_data.get("progress"),
        decisions=input_data.get("decisions", []),
        constraints=input_data.get("constraints", []),
        user_preferences=input_data.get("user_preferences", []),
        changed_files=input_data.get("changed_files", []),
        tool_results=input_data.get("tool_results", []),
        terminal_results=input_data.get("terminal_results", []),
        pinned_context=input_data.get("pinned_context", []),
        dropped_context_log=input_data.get("dropped_context_log", input_data.get("dropped_context", [])),
        memory_flush_refs=input_data.get("memory_flush_refs", []),
        next_steps=input_data.get("next_steps", []),
        critical_context=input_data.get("critical_context", []),
    )
    validation = validate_compact_packet(payload)
    if not validation.valid:
        return error("; ".join(validation.errors), code="INVALID_CONTEXT_PACKET")
    payload["validation"] = validation.to_dict()
    compact_id = payload["compact_id"]
    path = _context_root() / (compact_id + ".json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["content_ref"] = path.relative_to(_pack_root()).as_posix()
    dispatch_hook("after_compaction", payload)
    return ok(payload)
