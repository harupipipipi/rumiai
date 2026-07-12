from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ImageUnderstanding:
    summary: str = ""
    ocr_text: str = ""
    objects: list[str] = field(default_factory=list)
    layout: str = ""
    relevant_details: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    source_attachment_ids: list[str] = field(default_factory=list)
    generated_by: str = ""
    created_at: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_image_understanding(value: Any) -> dict[str, Any]:
    if isinstance(value, ImageUnderstanding):
        return value.to_dict()
    raw = value if isinstance(value, dict) else {}
    return ImageUnderstanding(
        summary=str(raw.get("summary") or ""),
        ocr_text=str(raw.get("ocr_text") or raw.get("ocr") or ""),
        objects=[str(item) for item in raw.get("objects", [])] if isinstance(raw.get("objects"), list) else [],
        layout=str(raw.get("layout") or ""),
        relevant_details=[str(item) for item in raw.get("relevant_details", [])] if isinstance(raw.get("relevant_details"), list) else [],
        uncertainties=[str(item) for item in raw.get("uncertainties", [])] if isinstance(raw.get("uncertainties"), list) else [],
        safety_notes=[str(item) for item in raw.get("safety_notes", [])] if isinstance(raw.get("safety_notes"), list) else [],
        source_attachment_ids=[str(item) for item in raw.get("source_attachment_ids", [])] if isinstance(raw.get("source_attachment_ids"), list) else [],
        generated_by=str(raw.get("generated_by") or ""),
        created_at=int(raw.get("created_at") or 0),
    ).to_dict()
