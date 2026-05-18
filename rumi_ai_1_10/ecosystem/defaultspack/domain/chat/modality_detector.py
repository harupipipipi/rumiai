from __future__ import annotations

from typing import Any


IMAGE_BLOCK_TYPES = {"image_url", "image"}


def detect_modalities(
    content: Any = None,
    metadata: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    blocks = content if isinstance(content, list) else [content] if content not in (None, "") else []
    metadata = metadata if isinstance(metadata, dict) else {}
    attachment_items = attachments if isinstance(attachments, list) else []
    for key in ("attachments", "workspace_attachments"):
        raw = metadata.get(key)
        if isinstance(raw, list):
            attachment_items.extend(item for item in raw if isinstance(item, dict))

    has_images = any(_block_is_image(block) for block in blocks) or any(_attachment_is_image(item) for item in attachment_items)
    has_files = any(_attachment_is_file(item) for item in attachment_items)
    has_text = any(_block_has_text(block) for block in blocks)
    image_attachment_ids = []
    for item in attachment_items:
        if _attachment_is_image(item):
            image_attachment_ids.append(str(item.get("id") or item.get("name") or "").strip())
    return {
        "has_text": has_text,
        "has_images": has_images,
        "has_files": has_files,
        "input_modalities": _dedupe(["text"] + (["image"] if has_images else []) + (["file"] if has_files else [])),
        "image_attachment_ids": [item for item in image_attachment_ids if item],
        "attachment_count": len(attachment_items),
    }


def strip_image_blocks_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        updated = dict(message)
        content = updated.get("content")
        if isinstance(content, list):
            filtered = [block for block in content if not _block_is_image(block)]
            if filtered:
                updated["content"] = filtered
            else:
                updated["content"] = ""
        stripped.append(updated)
    return stripped


def _block_is_image(block: Any) -> bool:
    return isinstance(block, dict) and str(block.get("type") or "") in IMAGE_BLOCK_TYPES


def _block_has_text(block: Any) -> bool:
    if isinstance(block, str):
        return bool(block.strip())
    return isinstance(block, dict) and str(block.get("type") or "text") == "text" and bool(str(block.get("text") or "").strip())


def _attachment_is_image(attachment: dict[str, Any]) -> bool:
    mime = str(attachment.get("type") or attachment.get("mime_type") or "").lower()
    return mime.startswith("image/")


def _attachment_is_file(attachment: dict[str, Any]) -> bool:
    return not _attachment_is_image(attachment)


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
