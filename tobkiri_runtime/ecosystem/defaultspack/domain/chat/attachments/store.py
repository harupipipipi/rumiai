from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from domain.chat.attachments.model import ATTACHMENT_SCHEMA_VERSION, AttachmentRecord
from domain.chat.attachments.representations import build_representations


MANIFEST_NAME = "attachments.v2.json"


def manifest_path(conversation_workspace_dir: Path) -> Path:
    return conversation_workspace_dir / "attachments" / MANIFEST_NAME


def load_attachment_records(conversation_workspace_dir: Path) -> list[AttachmentRecord]:
    path = manifest_path(conversation_workspace_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    records = raw.get("attachments") if isinstance(raw, dict) else []
    return [AttachmentRecord.from_dict(item) for item in records if isinstance(item, dict)]


def write_attachment_records(conversation_workspace_dir: Path, records: list[AttachmentRecord]) -> None:
    path = manifest_path(conversation_workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ATTACHMENT_SCHEMA_VERSION,
        "updated_at": int(time.time() * 1000),
        "attachments": [record.to_dict() for record in records],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_attachment_records(
    conversation_workspace_dir: Path,
    attachments: list[dict[str, Any]],
    legacy_refs: list[dict[str, Any]],
) -> list[AttachmentRecord]:
    existing = {record.id: record for record in load_attachment_records(conversation_workspace_dir)}
    now = int(time.time() * 1000)
    records: list[AttachmentRecord] = []
    for index, ref in enumerate(legacy_refs):
        if not isinstance(ref, dict):
            continue
        attachment = attachments[index] if index < len(attachments) and isinstance(attachments[index], dict) else {}
        record_id = str(ref.get("id") or attachment.get("id") or f"attachment-{index + 1}")
        workspace_path = str(ref.get("workspace_path") or "")
        previous = existing.get(record_id)
        provider_refs = dict((previous.provider_refs if previous else {}) or {})
        if isinstance(attachment.get("provider_refs"), dict):
            provider_refs.update(attachment["provider_refs"])
        record = AttachmentRecord(
            id=record_id,
            name=str(ref.get("name") or attachment.get("name") or record_id),
            mime_type=str(ref.get("type") or attachment.get("type") or attachment.get("mime_type") or ""),
            size=ref.get("size") if isinstance(ref.get("size"), int) else attachment.get("size") if isinstance(attachment.get("size"), int) else None,
            workspace_path=workspace_path,
            source=str(ref.get("source") or attachment.get("source") or ""),
            source_path=str(ref.get("sourcePath") or attachment.get("sourcePath") or attachment.get("source_path") or ""),
            representations=build_representations(attachment, workspace_path),
            provider_refs=provider_refs,
            created_at=previous.created_at if previous and previous.created_at else now,
        )
        existing[record_id] = record
        records.append(record)
    all_records = list(existing.values())
    write_attachment_records(conversation_workspace_dir, all_records)
    return records
