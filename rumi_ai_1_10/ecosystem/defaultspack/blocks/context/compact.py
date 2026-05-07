import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok


def _pack_root():
    return Path(__file__).resolve().parents[2]


def _context_root():
    root = _pack_root() / "user_data" / "context"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run(input_data, context=None):
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
    compact_id = "compact_" + str(uuid.uuid4())
    payload = {
        "compact_id": compact_id,
        "goal": input_data.get("goal", ""),
        "summary": str(summary),
        "pinned_context": input_data.get("pinned_context", []),
        "dropped_context": input_data.get("dropped_context", []),
        "changed_files": input_data.get("changed_files", []),
        "decisions": input_data.get("decisions", []),
        "next_steps": input_data.get("next_steps", []),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _context_root() / (compact_id + ".json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["content_ref"] = path.relative_to(_pack_root()).as_posix()
    return ok(payload)
