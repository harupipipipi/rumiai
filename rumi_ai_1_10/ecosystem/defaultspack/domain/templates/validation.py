from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import (
    RumiTemplate,
    TemplateDiagnostic,
    TemplateKind,
    TemplatePieceKind,
    TemplateStatus,
)
from .security import assess_template_security


@dataclass
class TemplateValidationResult:
    template: RumiTemplate | None
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.template is not None and not any(diagnostic.is_error for diagnostic in self.diagnostics)


def parse_template(
    raw: dict[str, Any],
    *,
    source_path: str | None = None,
    trust_level: str | None = None,
) -> TemplateValidationResult:
    if not isinstance(raw, dict):
        return TemplateValidationResult(
            None,
            [
                TemplateDiagnostic(
                    code="template.invalid_document",
                    message="template document must be a JSON object",
                    source_path=source_path,
                )
            ],
        )

    template = RumiTemplate.from_dict(raw, source_path=source_path, trust_level=trust_level)
    return TemplateValidationResult(template, validate_template(template, raw=raw))


def validate_template(template: RumiTemplate, *, raw: dict[str, Any] | None = None) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    diagnostics.extend(_validate_required(template, raw=raw))
    diagnostics.extend(_validate_enums(template))
    diagnostics.extend(_validate_pieces(template, raw=raw))
    diagnostics.extend(assess_template_security(template))
    return diagnostics


def has_errors(diagnostics: list[TemplateDiagnostic]) -> bool:
    return any(diagnostic.is_error for diagnostic in diagnostics)


def _validate_required(template: RumiTemplate, *, raw: dict[str, Any] | None) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    required = {
        "id": template.id,
        "kind": template.kind,
        "version": template.version,
        "status": template.status,
    }
    for field_name, value in required.items():
        if value is None or value == "":
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.missing_required",
                    message=f"{field_name} is required",
                    template_id=template.id or None,
                    path=f"/{field_name}",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )

    raw_pieces = raw.get("pieces") if raw is not None else None
    if raw is not None and "pieces" not in raw:
        diagnostics.append(
            TemplateDiagnostic(
                code="template.missing_required",
                message="pieces is required",
                template_id=template.id or None,
                path="/pieces",
                source_path=str(template.source_path) if template.source_path else None,
            )
        )
    elif raw_pieces is not None and not isinstance(raw_pieces, list):
        diagnostics.append(
            TemplateDiagnostic(
                code="template.invalid_pieces",
                message="pieces must be a list",
                template_id=template.id or None,
                path="/pieces",
                source_path=str(template.source_path) if template.source_path else None,
            )
        )
    return diagnostics


def _validate_enums(template: RumiTemplate) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    if not isinstance(template.kind, TemplateKind):
        diagnostics.append(_invalid_enum(template, "kind", template.kind, TemplateKind))
    if not isinstance(template.status, TemplateStatus):
        diagnostics.append(_invalid_enum(template, "status", template.status, TemplateStatus))
    return diagnostics


def _validate_pieces(template: RumiTemplate, *, raw: dict[str, Any] | None) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    seen: set[str] = set()
    raw_pieces = raw.get("pieces") if raw is not None and isinstance(raw.get("pieces"), list) else []

    for index, piece in enumerate(template.pieces):
        if not piece.id:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.missing_id",
                    message="piece id is required",
                    template_id=template.id,
                    piece_id=None,
                    path=f"/pieces/{index}/id",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
        elif piece.id in seen:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.duplicate_id",
                    message=f"duplicate piece id: {piece.id}",
                    severity="warning",
                    template_id=template.id,
                    piece_id=piece.id,
                    path=f"/pieces/{index}/id",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
        seen.add(piece.id)

        if not isinstance(piece.kind, TemplatePieceKind):
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.invalid_kind",
                    message=f"unsupported piece kind: {piece.kind}",
                    template_id=template.id,
                    piece_id=piece.id or None,
                    path=f"/pieces/{index}/kind",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )

    if raw_pieces and len(raw_pieces) != len(template.pieces):
        diagnostics.append(
            TemplateDiagnostic(
                code="template.piece.invalid_item",
                message="all pieces must be JSON objects",
                template_id=template.id,
                path="/pieces",
                source_path=str(template.source_path) if template.source_path else None,
            )
        )
    return diagnostics


def _invalid_enum(template: RumiTemplate, field_name: str, value: object, enum_type: type[Enum]) -> TemplateDiagnostic:
    allowed = ", ".join(item.value for item in enum_type)
    return TemplateDiagnostic(
        code=f"template.invalid_{field_name}",
        message=f"unsupported {field_name}: {value}; allowed: {allowed}",
        template_id=template.id or None,
        path=f"/{field_name}",
        source_path=str(template.source_path) if template.source_path else None,
    )
