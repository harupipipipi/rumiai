from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.chat.attachments.store import load_attachment_records, write_attachment_records


def cache_provider_ref(conversation_workspace_dir: Path, attachment_id: str, provider_id: str, file_id: str) -> None:
    records = load_attachment_records(conversation_workspace_dir)
    for record in records:
        if record.id == attachment_id:
            record.provider_refs[provider_id] = file_id
            record.representations.setdefault("provider_file_ids", {})[provider_id] = file_id
            write_attachment_records(conversation_workspace_dir, records)
            return


def provider_ref_for(conversation_workspace_dir: Path, attachment_id: str, provider_id: str) -> Any:
    for record in load_attachment_records(conversation_workspace_dir):
        if record.id == attachment_id:
            return record.provider_refs.get(provider_id)
    return None
