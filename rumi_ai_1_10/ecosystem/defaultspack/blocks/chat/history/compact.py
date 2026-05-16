"""
blocks/chat/history/compact.py - AI-driven automatic conversation compaction.

Analyzes the conversation to identify compactable segments (experiment logs,
verbose debug output, iterative trials) and replaces each with a concise
summary. Processes segments from last to first so that earlier indices
remain valid after each replacement.

Input:
    conversation_id: str (required)
    model: str (optional) - override model for AI calls
    max_context_tokens: int (optional) - target token budget hint
    dry_run: bool (optional, default false) - if true, return plan without executing

Returns:
    segments_processed, total_deleted, summary_messages, conversation
    (or trim_plan if dry_run)
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from blocks._common import ok, error

from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from domain.chat.history_editor import (
    replace_range_with_message,
    identify_compactable_segments,
    _build_text_from_content,
)
from blocks.chat.send import _ai_direct_complete


def _build_analysis_prompt(messages_with_ids, max_context_tokens=None):
    """Build the AI prompt that identifies segments to compact."""
    system_text = (
        "You are a conversation compaction analyst. Analyze the conversation and "
        "identify segments of messages that can be replaced by a brief summary "
        "without losing important information.\n\n"
        "Good candidates for compaction:\n"
        "- Intermediate experiment/work logs where only the conclusion matters\n"
        "- Step-by-step debug output that led to a fix\n"
        "- Repetitive trial-and-error sequences\n"
        "- Verbose tool outputs superseded by later summaries\n\n"
        "Do NOT compact:\n"
        "- The initial user request or problem statement\n"
        "- Final results, conclusions, or decisions\n"
        "- Important turning points in the conversation\n"
        "- The most recent 2 messages (they are still active context)\n\n"
    )
    if max_context_tokens is not None:
        system_text += (
            "Target: the conversation should fit within roughly "
            + str(max_context_tokens)
            + " tokens after compaction.\n\n"
        )
    system_text += (
        "Respond with a JSON array of segments. Each segment:\n"
        '{"start_id": "<message_id>", "end_id": "<message_id>", '
        '"reason": "<why>", "summary_preview": "<what the summary would say>"}\n\n'
        "If nothing should be compacted, respond with: []\n"
        "Output ONLY the JSON array."
    )

    lines = []
    for entry in messages_with_ids:
        msg_id = entry["id"]
        role = entry["role"]
        text = entry["content"]
        if not text:
            text = "(empty)"
        if isinstance(text, str) and len(text) > 300:
            text = text[:300] + "..."
        lines.append("[ID: " + msg_id + "] [" + role + "]: " + text)

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Analyze this conversation:\n\n" + "\n".join(lines)},
    ]


def _build_segment_summary_prompt(standard_messages, reason, summary_preview):
    """Build the AI prompt that generates a summary for one segment."""
    system_text = (
        "You are a conversation editor. Summarize the following conversation "
        "segment into a concise paragraph. Preserve all important results, "
        "conclusions, decisions, and data. Discard verbose intermediate work.\n"
        "Compaction reason: " + reason + "\n"
        "Expected summary direction: " + summary_preview + "\n\n"
        "Output ONLY the summary text."
    )

    parts = []
    for msg in standard_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            parts.append("[" + role + "]: " + content)

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Summarize:\n\n" + "\n".join(parts)},
    ]


def _parse_segments(response_text):
    """Parse the AI analysis response into a list of segment dicts."""
    text = response_text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        segments = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(segments, list):
        return []
    valid = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if "start_id" not in seg or "end_id" not in seg:
            continue
        valid.append({
            "start_id": str(seg["start_id"]),
            "end_id": str(seg["end_id"]),
            "reason": str(seg.get("reason", "")),
            "summary_preview": str(seg.get("summary_preview", "")),
        })
    return valid


def _extract_text(response):
    """Extract text from an AI response."""
    if isinstance(response, dict) and "data" in response:
        response = response["data"]
    content = response.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _call_ai(call_handler, model, messages):
    """Call AI and return (text, error_message)."""
    if call_handler is not None:
        try:
            ai_params = {
                "model": model,
                "messages": messages,
                "tools": [],
                "params": {},
            }
            response = call_handler("defaults.ai.complete", ai_params)
        except Exception as exc:
            return None, "AI request failed: " + str(exc)
        if isinstance(response, dict) and response.get("status") == "error":
            err = response.get("error", {})
            message = err.get("message") if isinstance(err, dict) else None
            return None, str(message or "AI request failed")
        if isinstance(response, dict) and response.get("status") == "ok":
            response = response.get("data", {})
    else:
        response, ai_error = _ai_direct_complete(model, messages, [], {})
        if ai_error is not None:
            return None, ai_error
    if not isinstance(response, dict):
        return None, "AI provider returned an invalid response"
    return _extract_text(response), None


def _unavailable_analysis():
    """Structured error used by legacy callers if AI analysis is unavailable."""
    return {
        "success": False,
        "error": "AI analysis is unavailable",
        "error_type": "not_implemented",
    }


def run(input_data, context):
    store = ChatStore()

    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")

    messages = conv.get("messages", [])
    if len(messages) < 3:
        return ok({
            "segments_processed": 0,
            "total_deleted": 0,
            "summary_messages": [],
            "conversation": conv,
            "message": "Too few messages to compact",
        })

    model = input_data.get("model", "default")
    if model == "default":
        model = conv.get("model", "stub/default")
    max_context_tokens = input_data.get("max_context_tokens")
    dry_run = input_data.get("dry_run", False)

    call_handler = context.get("call_handler") if context else None

    # --- Step 1: heuristic pre-filter ---
    heuristic_segments = identify_compactable_segments(messages)

    # --- Step 2: AI analysis for precise segment identification ---
    messages_with_ids = []
    for msg in messages:
        messages_with_ids.append({
            "id": msg.get("id", ""),
            "role": msg.get("role", "unknown"),
            "content": _build_text_from_content(msg.get("content", "")),
        })

    analysis_prompt = _build_analysis_prompt(messages_with_ids, max_context_tokens)
    analysis_text, ai_error = _call_ai(call_handler, model, analysis_prompt)
    if ai_error is not None:
        return error(ai_error, "AI_ERROR")
    ai_segments = _parse_segments(analysis_text)

    # --- Step 3: merge AI segments with heuristic segments ---
    msg_id_set = {m["id"] for m in messages}
    validated_segments = []
    seen_ranges = set()

    for seg in ai_segments:
        if seg["start_id"] in msg_id_set and seg["end_id"] in msg_id_set:
            key = (seg["start_id"], seg["end_id"])
            if key not in seen_ranges:
                seen_ranges.add(key)
                validated_segments.append(seg)

    for seg in heuristic_segments:
        key = (seg["start_id"], seg["end_id"])
        if key not in seen_ranges:
            if seg["start_id"] in msg_id_set and seg["end_id"] in msg_id_set:
                seen_ranges.add(key)
                validated_segments.append(seg)

    if not validated_segments:
        return ok({
            "segments_processed": 0,
            "total_deleted": 0,
            "summary_messages": [],
            "conversation": conv,
            "message": "No compactable segments found",
        })

    # --- Dry run: return plan only ---
    if dry_run:
        return ok({
            "trim_plan": {"segments": validated_segments},
            "conversation_id": conversation_id,
            "total_messages": len(messages),
        })

    # --- Step 4: sort segments by position (last first) to preserve indices ---
    msg_index = {}
    for idx, msg in enumerate(messages):
        msg_index[msg.get("id", "")] = idx

    def segment_sort_key(seg):
        return msg_index.get(seg["start_id"], 0)

    validated_segments.sort(key=segment_sort_key, reverse=True)

    # --- Step 5: process each segment ---
    total_deleted = 0
    summary_messages = []

    for seg in validated_segments:
        range_result = store.get_messages_range(
            conversation_id, seg["start_id"], seg["end_id"]
        )
        if range_result is None:
            continue

        range_msgs, start_idx = range_result
        if len(range_msgs) < 2:
            continue

        standard_msgs = convert_to_standard(range_msgs)
        summary_prompt = _build_segment_summary_prompt(
            standard_msgs,
            seg.get("reason", "compaction"),
            seg.get("summary_preview", ""),
        )
        summary_text, ai_error = _call_ai(call_handler, model, summary_prompt)
        if ai_error is not None:
            return error(ai_error, "AI_ERROR")

        summary_msg_dict = {
            "role": "assistant",
            "content": [{"type": "text", "text": summary_text}],
            "metadata": {
                "is_summary": True,
                "edit_type": "auto_compact",
                "original_message_count": len(range_msgs),
                "original_message_ids": [m["id"] for m in range_msgs],
                "compact_reason": seg.get("reason", ""),
            },
        }

        result, err = replace_range_with_message(
            store, conversation_id,
            seg["start_id"], seg["end_id"],
            summary_msg_dict,
        )
        if err is not None:
            continue

        total_deleted += result.get("deleted_count", 0)
        replacement_msg = result.get("replacement_message")
        if replacement_msg is not None:
            summary_messages.append(replacement_msg)

    updated_conv = store.get_conversation(conversation_id)
    return ok({
        "segments_processed": len(summary_messages),
        "total_deleted": total_deleted,
        "summary_messages": summary_messages,
        "conversation": updated_conv,
    })
