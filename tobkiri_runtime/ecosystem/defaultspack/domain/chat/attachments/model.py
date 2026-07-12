from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ATTACHMENT_SCHEMA_VERSION = "rumi.attachment.v2"


@dataclass
class AttachmentRecord:
    id: str
    name: str
    mime_type: str = ""
    size: int | None = None
    workspace_path: str = ""
    source: str = ""
    source_path: str = ""
    representations: dict[str, Any] = field(default_factory=dict)
    provider_refs: dict[str, Any] = field(default_factory=dict)
    created_at: int | None = None
    schema_version: str = ATTACHMENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
            "workspace_path": self.workspace_path,
            "source": self.source,
            "source_path": self.source_path,
            "representations": self.representations,
            "provider_refs": self.provider_refs,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AttachmentRecord":
        return cls(
            id=str(raw.get("id") or ""),
            name=str(raw.get("name") or ""),
            mime_type=str(raw.get("mime_type") or raw.get("type") or ""),
            size=raw.get("size") if isinstance(raw.get("size"), int) else None,
            workspace_path=str(raw.get("workspace_path") or ""),
            source=str(raw.get("source") or ""),
            source_path=str(raw.get("source_path") or raw.get("sourcePath") or ""),
            representations=dict(raw.get("representations") or {}),
            provider_refs=dict(raw.get("provider_refs") or {}),
            created_at=raw.get("created_at") if isinstance(raw.get("created_at"), int) else None,
            schema_version=str(raw.get("schema_version") or ATTACHMENT_SCHEMA_VERSION),
        )
