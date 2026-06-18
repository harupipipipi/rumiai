from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import (
    RumiTemplate,
    ResolvedTemplate,
    TemplateDependencySpec,
    TemplateDiagnostic,
    TemplatePiece,
    TemplateTrustLevel,
)
from .registry import TemplateRegistry
from .validation import parse_template, validate_template


RESERVED_PROJECTED_METADATA_FIELDS = {
    "trust_level",
    "template_id",
    "piece_id",
    "projected_id",
    "origin",
    "_source",
}


def resolve_template(template_id: str, registry: TemplateRegistry) -> ResolvedTemplate:
    return _resolve_template(template_id, registry, stack=[])


def merge_template_pieces(
    base_pieces: list[TemplatePiece],
    child_pieces: list[TemplatePiece],
    *,
    template_id: str | None = None,
) -> tuple[list[TemplatePiece], list[TemplateDiagnostic]]:
    merged = [deepcopy(piece) for piece in base_pieces]
    diagnostics: list[TemplateDiagnostic] = []
    index_by_id = {piece.id: index for index, piece in enumerate(merged)}

    for piece in child_pieces:
        piece_copy = deepcopy(piece)
        if piece_copy.id in index_by_id:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.duplicate_id",
                    message=f"duplicate piece id during merge: {piece_copy.id}",
                    severity="warning",
                    template_id=template_id,
                    piece_id=piece_copy.id,
                )
            )
            merged[index_by_id[piece_copy.id]] = piece_copy
            continue
        merged.append(piece_copy)
        index_by_id[piece_copy.id] = len(merged) - 1

    ordered, order_diagnostics = _order_pieces(merged, template_id=template_id)
    diagnostics.extend(order_diagnostics)
    return ordered, diagnostics


def apply_template_patches(
    template: RumiTemplate,
    patches: list[dict[str, Any]],
    *,
    trust_level: TemplateTrustLevel | str | None = None,
) -> tuple[RumiTemplate, list[TemplateDiagnostic]]:
    raw = template.to_dict()
    diagnostics: list[TemplateDiagnostic] = []
    for index, patch in enumerate(patches):
        diagnostic = _apply_patch(raw, patch, template_id=template.id, patch_index=index)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    effective_trust = trust_level if trust_level is not None else template.trust_level
    parsed = parse_template(
        raw,
        source_path=str(template.source_path) if template.source_path else None,
        trust_level=_value(effective_trust),
        declared_id=template.declared_id,
    )
    diagnostics.extend(parsed.diagnostics)
    return parsed.template or template, diagnostics


def diagnose_template_dependencies(
    template: RumiTemplate, registry: TemplateRegistry
) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    for dependency in template.dependencies:
        dependency_id = (
            dependency.id if isinstance(dependency, TemplateDependencySpec) else str(dependency)
        )
        if registry.get(dependency_id) is None:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.dependency.missing",
                    message=f"missing template dependency: {dependency_id}",
                    template_id=template.id,
                    path="/dependencies",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
    return diagnostics


def diagnose_capability_requirements(
    template: RumiTemplate, provided: set[str] | None = None
) -> list[TemplateDiagnostic]:
    provided = set(provided or set()) | set(template.capabilities.provides)
    diagnostics: list[TemplateDiagnostic] = []
    for capability in template.capabilities.requires:
        if capability not in provided:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.capability.missing",
                    message=f"missing required capability: {capability}",
                    template_id=template.id,
                    path="/capabilities/requires",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
    return diagnostics


def _resolve_template(
    template_id: str, registry: TemplateRegistry, *, stack: list[str]
) -> ResolvedTemplate:
    if template_id in stack:
        return ResolvedTemplate(
            None,
            [
                TemplateDiagnostic(
                    code="template.extends.cycle",
                    message=f"template extends cycle: {' -> '.join(stack + [template_id])}",
                    template_id=template_id,
                )
            ],
            ancestry=stack + [template_id],
        )

    template = registry.get(template_id)
    if template is None:
        return ResolvedTemplate(
            None,
            [
                TemplateDiagnostic(
                    code="template.registry.not_found",
                    message=f"template not found: {template_id}",
                    template_id=template_id,
                )
            ],
            ancestry=list(stack),
        )

    diagnostics: list[TemplateDiagnostic] = []
    ancestry = list(stack) + [template_id]
    bases = _extends_list(template.extends)
    resolved = deepcopy(template)
    inherited_provides: set[str] = set()

    if bases:
        if len(bases) > 1:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.extends.multiple",
                    message="multiple extends entries are resolved in listed order",
                    severity="warning",
                    template_id=template.id,
                    path="/extends",
                )
            )
        base_template: RumiTemplate | None = None
        for base_id in bases:
            base_resolved = _resolve_template(base_id, registry, stack=ancestry)
            diagnostics.extend(base_resolved.diagnostics)
            if base_resolved.template is None:
                continue
            inherited_provides.update(base_resolved.template.capabilities.provides)
            if base_template is not None:
                base_template, compose_diagnostics = _compose(base_template, base_resolved.template)
                diagnostics.extend(compose_diagnostics)
            else:
                base_template = base_resolved.template
        if base_template is not None:
            resolved, compose_diagnostics = _compose(base_template, template)
            diagnostics.extend(compose_diagnostics)
            ancestry = [*bases, template_id]
    else:
        resolved.pieces, order_diagnostics = _order_pieces(resolved.pieces, template_id=resolved.id)
        diagnostics.extend(order_diagnostics)

    if resolved.patches:
        resolved, patch_diagnostics = apply_template_patches(
            resolved, resolved.patches, trust_level=template.trust_level
        )
        diagnostics.extend(patch_diagnostics)
        resolved.pieces, order_diagnostics = _order_pieces(resolved.pieces, template_id=resolved.id)
        diagnostics.extend(order_diagnostics)

    diagnostics.extend(validate_template(resolved))
    diagnostics.extend(diagnose_template_dependencies(resolved, registry))
    diagnostics.extend(diagnose_capability_requirements(resolved, provided=inherited_provides))
    return ResolvedTemplate(resolved, diagnostics, ancestry=ancestry)


def _compose(
    base: RumiTemplate | None, child: RumiTemplate
) -> tuple[RumiTemplate, list[TemplateDiagnostic]]:
    if base is None:
        return deepcopy(child), []
    raw = base.to_dict()
    child_raw = child.to_dict()
    raw.update(
        {
            key: value
            for key, value in child_raw.items()
            if key not in {"pieces", "capabilities", "dependencies", "conflicts"}
        }
    )
    raw["dependencies"] = _merge_dependency_specs(base.dependencies, child.dependencies)
    raw["conflicts"] = _merge_dependency_specs(base.conflicts, child.conflicts)
    raw["capabilities"] = {
        "provides": sorted(set(base.capabilities.provides) | set(child.capabilities.provides)),
        "requires": sorted(set(base.capabilities.requires) | set(child.capabilities.requires)),
        "permissions": sorted(
            set(base.capabilities.permissions) | set(child.capabilities.permissions)
        ),
    }
    pieces, diagnostics = merge_template_pieces(base.pieces, child.pieces, template_id=child.id)
    raw["pieces"] = [piece.to_dict() for piece in pieces]
    parsed = parse_template(
        raw,
        source_path=str(child.source_path) if child.source_path else None,
        declared_id=child.declared_id,
    )
    diagnostics.extend(parsed.diagnostics)
    return parsed.template or child, diagnostics


def _merge_dependency_specs(
    base: list[TemplateDependencySpec],
    child: list[TemplateDependencySpec],
) -> list[str | dict[str, Any]]:
    merged: dict[str, TemplateDependencySpec] = {}
    order: list[str] = []
    for spec in [*base, *child]:
        spec_id = str(spec.id or "").strip()
        if not spec_id:
            continue
        if spec_id not in merged:
            order.append(spec_id)
        merged[spec_id] = spec
    return [merged[spec_id].to_value() for spec_id in order]


def _extends_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _order_pieces(
    pieces: list[TemplatePiece],
    *,
    template_id: str | None = None,
) -> tuple[list[TemplatePiece], list[TemplateDiagnostic]]:
    diagnostics: list[TemplateDiagnostic] = []
    piece_ids = {piece.id for piece in pieces}
    edges: dict[str, set[str]] = {piece.id: set() for piece in pieces}
    indegree: dict[str, int] = {piece.id: 0 for piece in pieces}
    position = {piece.id: index for index, piece in enumerate(pieces)}
    position_rank: dict[str, float] = {piece.id: float(index) for index, piece in enumerate(pieces)}
    by_id = {piece.id: piece for piece in pieces}

    def add_edge(before_id: str, after_id: str, piece: TemplatePiece, path: str) -> None:
        if before_id not in piece_ids or after_id not in piece_ids:
            missing = before_id if before_id not in piece_ids else after_id
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.unknown_order_anchor",
                    message=f"piece ordering anchor does not exist: {missing}",
                    severity="warning",
                    template_id=template_id,
                    piece_id=piece.id,
                    path=path,
                )
            )
            return
        if after_id not in edges[before_id]:
            edges[before_id].add(after_id)
            indegree[after_id] += 1

    for piece in pieces:
        if piece.insert_before:
            add_edge(piece.id, piece.insert_before, piece, "/pieces/insert_before")
            if piece.insert_before in position:
                position_rank[piece.id] = position[piece.insert_before] - 0.1
        if piece.insert_after:
            add_edge(piece.insert_after, piece.id, piece, "/pieces/insert_after")
            if piece.insert_after in position:
                position_rank[piece.id] = position[piece.insert_after] + 0.1
        if not piece.insert_before and not piece.insert_after and piece.slot in piece_ids:
            add_edge(str(piece.slot), piece.id, piece, "/pieces/slot")
            if str(piece.slot) in position:
                position_rank[piece.id] = position[str(piece.slot)] + 0.1
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.piece.legacy_slot_anchor",
                    message=(
                        "piece slot matched an existing piece id and was treated as "
                        "legacy insert_after"
                    ),
                    severity="warning",
                    template_id=template_id,
                    piece_id=piece.id,
                    path="/pieces/slot",
                )
            )

    def sort_key(piece_id: str) -> tuple[bool, int, float, str]:
        piece = by_id[piece_id]
        return (
            piece.order is None,
            piece.order if piece.order is not None else 0,
            position_rank[piece_id],
            piece_id,
        )

    ready = sorted([piece_id for piece_id, count in indegree.items() if count == 0], key=sort_key)
    ordered_ids: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered_ids.append(current)
        for after_id in sorted(edges[current], key=sort_key):
            indegree[after_id] -= 1
            if indegree[after_id] == 0:
                ready.append(after_id)
                ready.sort(key=sort_key)
    if len(ordered_ids) != len(pieces):
        cycle_ids = sorted(piece_id for piece_id, count in indegree.items() if count > 0)
        diagnostics.append(
            TemplateDiagnostic(
                code="template.piece.ordering_cycle",
                message=f"piece ordering cycle: {' -> '.join(cycle_ids)}",
                template_id=template_id,
                path="/pieces",
                details={"piece_ids": cycle_ids},
            )
        )
        return pieces, diagnostics
    return [by_id[piece_id] for piece_id in ordered_ids], diagnostics


def _apply_patch(
    raw: dict[str, Any], patch: dict[str, Any], *, template_id: str, patch_index: int
) -> TemplateDiagnostic | None:
    op = patch.get("op")
    path = patch.get("path")
    if (
        op not in {"replace", "add", "remove"}
        or not isinstance(path, str)
        or not path.startswith("/")
    ):
        return TemplateDiagnostic(
            code="template.patch.invalid",
            message="patch must contain op replace/add/remove and JSON pointer path",
            template_id=template_id,
            path=f"/patches/{patch_index}",
        )
    protected_field = _protected_patch_field(path)
    if protected_field:
        return TemplateDiagnostic(
            code="template.patch.protected_path",
            message=f"patch cannot modify immutable template field: {protected_field}",
            template_id=template_id,
            path=f"/patches/{patch_index}",
        )
    reserved_piece_field = _reserved_piece_metadata_patch_field(path, patch)
    if reserved_piece_field:
        return TemplateDiagnostic(
            code="template.patch.reserved_piece_metadata",
            message=f"patch cannot write reserved projected piece metadata: {reserved_piece_field}",
            template_id=template_id,
            path=f"/patches/{patch_index}",
        )

    try:
        parent, token = _resolve_pointer_parent(raw, path)
        if op == "remove":
            _remove_value(parent, token)
        elif op == "replace":
            _replace_value(parent, token, patch.get("value"))
        else:
            _add_value(parent, token, patch.get("value"))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return TemplateDiagnostic(
            code="template.patch.apply_failed",
            message=f"failed to apply patch at {path}: {exc}",
            template_id=template_id,
            path=f"/patches/{patch_index}",
        )
    return None


def _protected_patch_field(pointer: str) -> str | None:
    tokens = [_unescape_pointer(token) for token in pointer.strip("/").split("/") if token != ""]
    if not tokens:
        return None
    if tokens[0] in {"declared_id", "id", "trust_level"}:
        return tokens[0]
    if len(tokens) >= 2 and tokens[:2] == ["metadata", "declared_id"]:
        return "metadata/declared_id"
    return None


def _reserved_piece_metadata_patch_field(pointer: str, patch: dict[str, Any]) -> str | None:
    tokens = [_unescape_pointer(token) for token in pointer.strip("/").split("/") if token != ""]
    if not tokens or tokens[0] != "pieces":
        return None
    if len(tokens) >= 3 and tokens[2] in RESERVED_PROJECTED_METADATA_FIELDS:
        return f"pieces/*/{tokens[2]}"
    value = patch.get("value")
    if len(tokens) <= 2 and isinstance(value, dict):
        for field_name in RESERVED_PROJECTED_METADATA_FIELDS:
            if field_name in value:
                return f"pieces/*/{field_name}"
    return None


def _resolve_pointer_parent(raw: Any, pointer: str) -> tuple[Any, str]:
    tokens = [_unescape_pointer(token) for token in pointer.strip("/").split("/") if token != ""]
    if not tokens:
        raise ValueError("patching the document root is not supported")
    current = raw
    for token in tokens[:-1]:
        current = _get_child(current, token)
    return current, tokens[-1]


def _get_child(current: Any, token: str) -> Any:
    if isinstance(current, list):
        return current[_list_index(token, len(current))]
    if isinstance(current, dict):
        return current[token]
    raise TypeError("pointer traversed a scalar value")


def _replace_value(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        parent[_list_index(token, len(parent))] = value
    else:
        if token not in parent:
            raise KeyError(token)
        parent[token] = value


def _add_value(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        if token == "-":
            parent.append(value)
        else:
            parent.insert(_list_index(token, len(parent), allow_end=True), value)
    else:
        parent[token] = value


def _remove_value(parent: Any, token: str) -> None:
    if isinstance(parent, list):
        del parent[_list_index(token, len(parent))]
    else:
        del parent[token]


def _list_index(token: str, length: int, *, allow_end: bool = False) -> int:
    if not token.isdigit():
        raise IndexError(f"invalid list index: {token}")
    index = int(token)
    upper_bound = length if allow_end else length - 1
    if index > upper_bound:
        raise IndexError(f"list index out of range: {token}")
    return index


def _unescape_pointer(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)
