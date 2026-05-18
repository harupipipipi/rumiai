from __future__ import annotations

import json
import time
from typing import Any

from domain.chat.modality_detector import strip_image_blocks_from_messages
from domain.vision.image_summary_schema import ImageUnderstanding, normalize_image_understanding


VISION_BRIDGE_CONTEXT_HEADER = "[画像理解結果]"


def describe_images(
    *,
    messages: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    conversation_context: str = "",
    model: str = "",
    call_handler: Any = None,
) -> dict[str, Any]:
    attachment_ids = _attachment_ids(attachments)
    prompt = _bridge_prompt(conversation_context)
    if call_handler is not None and model:
        try:
            response = call_handler(
                "defaults.ai.complete",
                {
                    "model": model,
                    "messages": _vision_messages(messages or [], prompt),
                    "tools": [],
                    "params": {
                        "response_format": {"type": "json_object"},
                        "thinking_level": "none",
                    },
                },
            )
            parsed = _parse_ai_response(response)
            if parsed:
                parsed["generated_by"] = model
                parsed["created_at"] = int(time.time() * 1000)
                parsed.setdefault("source_attachment_ids", attachment_ids)
                return normalize_image_understanding(parsed)
        except Exception:
            pass
    fallback = ImageUnderstanding(
        summary="画像が添付されています。現在の環境では画像対応モデルによる詳細解析は未実行です。",
        ocr_text="",
        objects=[],
        layout="画像添付あり",
        relevant_details=["メインモデルが画像非対応の場合、この要約をテキスト文脈として使用します。"],
        uncertainties=["画像内容の詳細、OCR、細部の読み取りは未確認です。"],
        safety_notes=[],
        source_attachment_ids=attachment_ids,
        generated_by=model,
        created_at=int(time.time() * 1000),
    )
    return fallback.to_dict()


def bridge_context_text(understanding: dict[str, Any]) -> str:
    data = normalize_image_understanding(understanding)
    parts = [
        VISION_BRIDGE_CONTEXT_HEADER,
        "この会話では画像が添付されているが、現在のメインモデルは画像入力に対応していない。",
        "画像対応モデルまたはVision Bridgeが以下の内容を読み取った。",
        "",
        "概要:",
        data.get("summary") or "(概要なし)",
    ]
    if data.get("ocr_text"):
        parts.extend(["", "OCR:", str(data["ocr_text"])])
    if data.get("relevant_details"):
        parts.extend(["", "重要情報:"])
        parts.extend("- " + str(item) for item in data["relevant_details"])
    if data.get("uncertainties"):
        parts.extend(["", "不確実な点:"])
        parts.extend("- " + str(item) for item in data["uncertainties"])
    return "\n".join(parts)


def apply_vision_bridge_to_messages(messages: list[dict[str, Any]], understanding: dict[str, Any]) -> list[dict[str, Any]]:
    stripped = strip_image_blocks_from_messages(messages)
    context_message = {"role": "system", "content": bridge_context_text(understanding)}
    insert_at = 1 if stripped and stripped[0].get("role") == "system" else 0
    stripped.insert(insert_at, context_message)
    return stripped


def conversation_image_context(understanding: dict[str, Any]) -> dict[str, Any]:
    data = normalize_image_understanding(understanding)
    return {
        "generated_by": data.get("generated_by", ""),
        "created_at": data.get("created_at", int(time.time() * 1000)),
        "attachments": list(data.get("source_attachment_ids") or []),
        "summary": data.get("summary", ""),
        "ocr_text": data.get("ocr_text", ""),
        "valid_for_models_without_vision": True,
    }


def _bridge_prompt(conversation_context: str) -> str:
    return (
        "添付画像を読み取り、JSONだけで返してください。"
        " keys: summary, ocr_text, objects, layout, relevant_details, uncertainties, safety_notes, source_attachment_ids."
        "\n会話文脈:\n"
        + str(conversation_context or "")[:4000]
    )


def _vision_messages(messages: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    result = list(messages)
    result.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
    return result


def _parse_ai_response(response: Any) -> dict[str, Any] | None:
    data = response.get("data") if isinstance(response, dict) and response.get("status") == "ok" else response
    if not isinstance(data, dict):
        return None
    content = data.get("content")
    text = ""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += str(block.get("text") or "")
            elif isinstance(block, str):
                text += block
    elif isinstance(content, str):
        text = content
    elif isinstance(data.get("summary"), str):
        return data
    if not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"summary": text.strip(), "uncertainties": ["Vision model returned non-JSON text."]}
    return parsed if isinstance(parsed, dict) else None


def _attachment_ids(attachments: list[dict[str, Any]] | None) -> list[str]:
    result = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        value = str(attachment.get("id") or attachment.get("name") or "").strip()
        if value:
            result.append(value)
    return result
