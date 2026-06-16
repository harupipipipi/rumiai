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
    TemplateTrustLevel,
)
from .security import assess_template_security


BUILTIN_SETTINGS_FIELD_RENDERERS = {
    "api_key_setup",
    "checkbox",
    "model_api_routes",
    "model_select",
    "number",
    "provider_select",
    "select",
    "text",
    "textarea",
    "toggle",
}
BUILTIN_SHELL_RENDERERS = {
    "activity_preview",
    "chat_header",
    "chat_messages",
    "composer",
    "history_board",
    "right_sidebar",
    "settings_modal",
    "title_bar",
}
BUILTIN_SHELL_REGIONS = {
    "activity_preview",
    "chat_header",
    "chat_messages",
    "composer",
    "history",
    "right_sidebar",
    "settings_modal",
    "title_bar",
}
TRUSTED_SHELL_RENDERER_MODULE_PREFIXES = (
    "/static/renderers/",
    "/static/assets/renderers/",
    "/static/user_renderers/",
)


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
    diagnostics.extend(_validate_references(template))
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


def _validate_references(template: RumiTemplate) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    trust_level = _value(template.trust_level)
    renderer_types: set[str] = set(BUILTIN_SETTINGS_FIELD_RENDERERS)
    shell_renderer_ids: set[str] = set(BUILTIN_SHELL_RENDERERS)
    shell_region_ids: set[str] = set(BUILTIN_SHELL_REGIONS)
    permission_ids: set[str] = set()
    action_ids: dict[str, str] = {}
    data_source_ids: dict[str, str] = {}

    for piece in template.pieces:
        kind = _value(piece.kind)
        if kind == TemplatePieceKind.SHELL_RENDERER.value:
            renderer_id = _piece_payload_id(piece, "renderer", "renderer_id", "shell_renderer_id")
            if renderer_id:
                shell_renderer_ids.add(renderer_id)
        elif kind == TemplatePieceKind.SHELL_REGION.value:
            region_id = _piece_payload_id(piece, "region", "region_id", "shell_region_id")
            if region_id:
                shell_region_ids.add(region_id)

    for index, piece in enumerate(template.pieces):
        kind = _value(piece.kind)
        if trust_level != TemplateTrustLevel.BUILTIN.value:
            for field_name, value in (("entrypoint", piece.entrypoint), ("handler_ref", piece.data.get("handler_ref"))):
                if not str(value or "").strip():
                    continue
                diagnostics.append(
                    TemplateDiagnostic(
                        code="template.reference.non_builtin_handler_not_executable",
                        message=f"{field_name} is metadata only for non-builtin templates and is not executable by default",
                        severity="warning",
                        template_id=template.id,
                        piece_id=piece.id,
                        path=f"/pieces/{index}/{field_name}",
                        source_path=str(template.source_path) if template.source_path else None,
                    )
                )

        if kind == TemplatePieceKind.FIELD_RENDERER.value:
            field_types = _field_renderer_types(piece.data)
            if not field_types:
                diagnostics.append(
                    TemplateDiagnostic(
                        code="template.reference.field_renderer_missing_field_types",
                        message="field_renderer.field_types must declare at least one field type",
                        template_id=template.id,
                        piece_id=piece.id,
                        path=f"/pieces/{index}/field_types",
                        source_path=str(template.source_path) if template.source_path else None,
                    )
                )
            renderer_types.update(field_types)

        if kind == TemplatePieceKind.COMPOSER_COMMAND.value:
            diagnostics.extend(_validate_composer_command(template, piece, index))

        if kind == TemplatePieceKind.COMPOSER_INPUT.value:
            diagnostics.extend(
                _validate_composer_input(
                    template,
                    piece,
                    index,
                    shell_region_ids=shell_region_ids,
                    shell_renderer_ids=shell_renderer_ids,
                )
            )

        if kind == TemplatePieceKind.SHELL_RENDERER.value:
            diagnostics.extend(_validate_shell_renderer(template, piece, index, trust_level=trust_level))

        if kind == TemplatePieceKind.SHELL_REGION.value:
            diagnostics.extend(
                _validate_shell_region(
                    template,
                    piece,
                    index,
                    shell_renderer_ids=shell_renderer_ids,
                )
            )

        if kind == TemplatePieceKind.CONTEXT_POLICY.value:
            diagnostics.extend(_validate_context_policy(template, piece, index))

        if kind == TemplatePieceKind.PERMISSION.value:
            permission_id = str(piece.data.get("permission_id") or piece.id or "").strip()
            if permission_id:
                permission_ids.add(permission_id)

        if _is_action_piece(kind, piece.data):
            _record_unique_id(
                diagnostics,
                action_ids,
                str(piece.data.get("action_id") or piece.data.get("command_id") or piece.id or "").strip(),
                template=template,
                piece_id=piece.id,
                path=f"/pieces/{index}/action_id",
                code="template.reference.duplicate_action_id",
                label="action id",
            )

        if _is_data_source_piece(kind, piece.data):
            _record_unique_id(
                diagnostics,
                data_source_ids,
                str(piece.data.get("data_source") or piece.data.get("source") or piece.id or "").strip(),
                template=template,
                piece_id=piece.id,
                path=f"/pieces/{index}/data_source",
                code="template.reference.duplicate_data_source_id",
                label="data source id",
            )

        route_metadata = piece.data.get("route_metadata")
        if kind == TemplatePieceKind.TEST_CONTRACT.value and isinstance(route_metadata, dict):
            method = str(route_metadata.get("method") or "").strip()
            path = str(route_metadata.get("path") or route_metadata.get("route_path") or "").strip()
            if not method or not path:
                diagnostics.append(
                    TemplateDiagnostic(
                        code="template.reference.route_metadata_missing_method_path",
                        message="test_contract.route_metadata must include method and path",
                        template_id=template.id,
                        piece_id=piece.id,
                        path=f"/pieces/{index}/route_metadata",
                        source_path=str(template.source_path) if template.source_path else None,
                    )
                )

    for index, piece in enumerate(template.pieces):
        if _value(piece.kind) != TemplatePieceKind.SETTINGS_FIELD.value:
            continue
        field_type = str(piece.data.get("field_type") or piece.data.get("type") or "").strip()
        if field_type and field_type not in renderer_types:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.reference.settings_field_renderer_missing",
                    message=f"settings field type has no renderer: {field_type}",
                    template_id=template.id,
                    piece_id=piece.id,
                    path=f"/pieces/{index}/type",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )

    capability_permissions = set(template.capabilities.permissions)
    for permission_id in sorted(capability_permissions - permission_ids):
        diagnostics.append(
            TemplateDiagnostic(
                code="template.reference.permission_missing_piece",
                message=f"capability permission has no permission piece: {permission_id}",
                template_id=template.id,
                path="/capabilities/permissions",
                source_path=str(template.source_path) if template.source_path else None,
            )
        )
    if capability_permissions:
        for permission_id in sorted(permission_ids - capability_permissions):
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.reference.permission_not_declared",
                    message=f"permission piece is not declared in capabilities.permissions: {permission_id}",
                    template_id=template.id,
                    path="/pieces/*/permission_id",
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


def _validate_composer_command(
    template: RumiTemplate,
    piece: Any,
    index: int,
) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    command = _piece_payload(piece, "command")
    command_id = _payload_id(command, piece, "command_id")
    if not command_id:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.command_missing_id_name",
                message="composer_command must include id or name",
                field="id",
                nested_key="command",
            )
        )

    execution = command.get("execution")
    if not isinstance(execution, dict) or not execution:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.command_missing_execution",
                message="composer_command.execution must be a non-empty object",
                field="execution",
                nested_key="command",
            )
        )
        return diagnostics

    execution_type = str(execution.get("type") or "").strip()
    if not execution_type:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.command_execution_missing_type",
                message="composer_command.execution.type is required",
                field="execution/type",
                nested_key="command",
            )
        )
    if execution_type in {"pack_block", "rumi_function"} and not str(execution.get("qualified_name") or "").strip():
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.command_execution_missing_qualified_name",
                message=f"composer_command.execution.qualified_name is required for {execution_type}",
                field="execution/qualified_name",
                nested_key="command",
            )
        )
    return diagnostics


def _validate_composer_input(
    template: RumiTemplate,
    piece: Any,
    index: int,
    *,
    shell_region_ids: set[str],
    shell_renderer_ids: set[str],
) -> list[TemplateDiagnostic]:
    data = _piece_payload(piece, "input")
    diagnostics: list[TemplateDiagnostic] = []
    region_id = _first_string(data, "region_id", "shell_region_id", "shell_region", "region")
    renderer_id = _first_string(data, "renderer_id", "shell_renderer_id", "renderer")
    if not region_id and not renderer_id:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.composer_input_missing_reference",
                message="composer_input must reference a region_id, shell region, or renderer",
                field="region_id",
                nested_key="input",
            )
        )
    if region_id and region_id not in shell_region_ids:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.composer_input_unknown_region",
                message=f"composer_input references unknown shell region: {region_id}",
                field="region_id",
                nested_key="input",
            )
        )
    if renderer_id and renderer_id not in shell_renderer_ids:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.composer_input_unknown_renderer",
                message=f"composer_input references unknown shell renderer: {renderer_id}",
                field="renderer",
                nested_key="input",
            )
        )
    return diagnostics


def _validate_shell_renderer(
    template: RumiTemplate,
    piece: Any,
    index: int,
    *,
    trust_level: str,
) -> list[TemplateDiagnostic]:
    data = _piece_payload(piece, "renderer")
    diagnostics: list[TemplateDiagnostic] = []
    module = data.get("module")
    if module is None:
        return diagnostics
    if trust_level != TemplateTrustLevel.BUILTIN.value:
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.shell_renderer_module_requires_builtin",
                message="shell_renderer.module is only executable for builtin templates",
                field="module",
                nested_key="renderer",
            )
        )
    if not _is_trusted_renderer_module(module):
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.shell_renderer_untrusted_module",
                message="shell_renderer.module must be a trusted static renderer path",
                field="module",
                nested_key="renderer",
            )
        )
    if data.get("trust") != "local":
        diagnostics.append(
            _piece_diagnostic(
                template,
                piece,
                index,
                code="template.reference.shell_renderer_missing_local_trust",
                message="shell_renderer.module requires trust='local'",
                field="trust",
                nested_key="renderer",
            )
        )
    return diagnostics


def _validate_shell_region(
    template: RumiTemplate,
    piece: Any,
    index: int,
    *,
    shell_renderer_ids: set[str],
) -> list[TemplateDiagnostic]:
    data = _piece_payload(piece, "region")
    renderer_id = str(data.get("renderer") or data.get("renderer_id") or data.get("shell_renderer_id") or "").strip()
    if not renderer_id or renderer_id in shell_renderer_ids:
        return []
    return [
        _piece_diagnostic(
            template,
            piece,
            index,
            code="template.reference.shell_region_unknown_renderer",
            message=f"shell_region references unknown shell renderer: {renderer_id}",
            field="renderer",
            nested_key="region",
        )
    ]


def _validate_context_policy(
    template: RumiTemplate,
    piece: Any,
    index: int,
) -> list[TemplateDiagnostic]:
    data = _piece_payload(piece, "policy")
    mode = str(data.get("mode") or data.get("policy_mode") or "").strip()
    if mode:
        return []
    return [
        _piece_diagnostic(
            template,
            piece,
            index,
            code="template.reference.context_policy_missing_mode",
            message="context_policy.mode is required",
            field="mode",
            nested_key="policy",
        )
    ]


def _field_renderer_types(data: dict[str, Any]) -> set[str]:
    raw = data.get("field_types")
    if isinstance(raw, list):
        return {str(value).strip() for value in raw if str(value or "").strip()}
    field_type = str(data.get("field_type") or data.get("type") or "").strip()
    return {field_type} if field_type else set()


def _is_action_piece(kind: str, data: dict[str, Any]) -> bool:
    return str(data.get("role") or "").strip() == "action" or (
        kind == TemplatePieceKind.FUNCTION.value and any(key in data for key in ("action", "action_id", "command_id"))
    )


def _is_data_source_piece(kind: str, data: dict[str, Any]) -> bool:
    return str(data.get("role") or "").strip() == "data_source" or (
        kind == TemplatePieceKind.FUNCTION.value and any(key in data for key in ("data_source", "source", "query"))
    )


def _record_unique_id(
    diagnostics: list[TemplateDiagnostic],
    seen: dict[str, str],
    item_id: str,
    *,
    template: RumiTemplate,
    piece_id: str,
    path: str,
    code: str,
    label: str,
) -> None:
    if not item_id:
        return
    if item_id in seen:
        diagnostics.append(
            TemplateDiagnostic(
                code=code,
                message=f"duplicate {label}: {item_id}",
                template_id=template.id,
                piece_id=piece_id,
                path=path,
                source_path=str(template.source_path) if template.source_path else None,
            )
        )
        return
    seen[item_id] = piece_id


def _piece_payload(piece: Any, nested_key: str) -> dict[str, Any]:
    nested = piece.data.get(nested_key)
    if isinstance(nested, dict):
        return dict(nested)
    return dict(piece.data)


def _piece_payload_id(piece: Any, nested_key: str, *aliases: str) -> str:
    return _payload_id(_piece_payload(piece, nested_key), piece, *aliases)


def _payload_id(data: dict[str, Any], piece: Any, *aliases: str) -> str:
    for key in (*aliases, "id", "name"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return str(piece.id or "").strip()


def _first_string(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _piece_diagnostic(
    template: RumiTemplate,
    piece: Any,
    index: int,
    *,
    code: str,
    message: str,
    field: str,
    nested_key: str,
) -> TemplateDiagnostic:
    return TemplateDiagnostic(
        code=code,
        message=message,
        template_id=template.id,
        piece_id=piece.id or None,
        path=_piece_path(piece, index, field, nested_key=nested_key),
        source_path=str(template.source_path) if template.source_path else None,
    )


def _piece_path(piece: Any, index: int, field: str, *, nested_key: str) -> str:
    if isinstance(piece.data.get(nested_key), dict):
        return f"/pieces/{index}/{nested_key}/{field}"
    return f"/pieces/{index}/{field}"


def _is_trusted_renderer_module(module: Any) -> bool:
    return isinstance(module, str) and module.startswith(TRUSTED_SHELL_RENDERER_MODULE_PREFIXES)


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)
