from __future__ import annotations

import json
from typing import Any

from domain.chat.ir_blocks import RumiIRBlock, RumiToolResultIR


MAX_INLINE_TOOL_RESULT_CHARS = 24_000


def encode_tool_result_to_ir_blocks(result: Any, *, tool_call_id: str = "", name: str = "") -> list[RumiIRBlock]:
    artifacts = _extract_artifacts(result)
    approval_required = _approval_required(result)
    text = _result_text(result)
    if len(text) > MAX_INLINE_TOOL_RESULT_CHARS:
        artifacts.append({"type": "truncated_text", "chars": len(text)})
        text = text[:MAX_INLINE_TOOL_RESULT_CHARS] + "\n...[truncated]"
    blocks = [
        RumiIRBlock(
            type="tool_result",
            tool_result=RumiToolResultIR(
                tool_call_id=tool_call_id,
                name=name,
                content=text,
                is_error=_is_error(result),
                approval_required=approval_required,
                artifacts=artifacts,
            ),
        )
    ]
    for artifact in artifacts:
        mime = str(artifact.get("mime_type") or artifact.get("type") or "")
        if mime.startswith("image/") or artifact.get("kind") == "image":
            blocks.append(RumiIRBlock(type="image", data={"artifact": artifact}))
        elif artifact.get("path"):
            blocks.append(RumiIRBlock(type="file", data={"artifact": artifact}))
    return blocks


def _result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("content", "text", "result", "output", "summary"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        data = result.get("data")
        if isinstance(data, dict):
            for key in ("content", "text", "result", "output", "summary"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def _extract_artifacts(result: Any) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    roots = [result]
    if isinstance(result, dict):
        roots.extend(value for value in (result.get("data"), result.get("result")) if isinstance(value, dict))
    for root in roots:
        if not isinstance(root, dict):
            continue
        for key in ("artifacts", "artifact_paths", "files"):
            value = root.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        artifacts.append(dict(item))
                    elif isinstance(item, str):
                        artifacts.append({"path": item})
    return artifacts


def _approval_required(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("approval_required") or result.get("requires_approval"):
        return True
    data = result.get("data")
    return isinstance(data, dict) and bool(data.get("approval_required") or data.get("requires_approval"))


def _is_error(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error" or result.get("is_error"):
        return True
    data = result.get("data")
    return isinstance(data, dict) and bool(data.get("is_error"))
