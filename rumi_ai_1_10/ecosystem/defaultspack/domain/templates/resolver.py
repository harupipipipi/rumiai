from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import RumiTemplate, ResolvedTemplate, TemplateDiagnostic, TemplatePiece
from .registry import TemplateRegistry
from .validation import parse_template, validate_template


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

        insert_at = _slot_insert_index(merged, piece_copy.slot)
        if insert_at is None:
            merged.append(piece_copy)
            index_by_id[piece_copy.id] = len(merged) - 1
        else:
            merged.insert(insert_at, piece_copy)
            index_by_id = {item.id: index for index, item in enumerate(merged)}

    return _order_pieces(merged), diagnostics


def apply_template_patches(template: RumiTemplate, patches: list[dict[str, Any]]) -> tuple[RumiTemplate, list[TemplateDiagnostic]]:
    raw = template.to_dict()
    diagnostics: list[TemplateDiagnostic] = []
    for index, patch in enumerate(patches):
        diagnostic = _apply_patch(raw, patch, template_id=template.id, patch_index=index)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    parsed = parse_template(raw, source_path=str(template.source_path) if template.source_path else None)
    diagnostics.extend(parsed.diagnostics)
    return parsed.template or template, diagnostics


def diagnose_template_dependencies(template: RumiTemplate, registry: TemplateRegistry) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    for dependency in template.dependencies:
        if registry.get(dependency) is None:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.dependency.missing",
                    message=f"missing template dependency: {dependency}",
                    template_id=template.id,
                    path="/dependencies",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
    return diagnostics


def diagnose_capability_requirements(template: RumiTemplate, provided: set[str] | None = None) -> list[TemplateDiagnostic]:
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


def _resolve_template(template_id: str, registry: TemplateRegistry, *, stack: list[str]) -> ResolvedTemplate:
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

    if resolved.patches:
        resolved, patch_diagnostics = apply_template_patches(resolved, resolved.patches)
        diagnostics.extend(patch_diagnostics)

    diagnostics.extend(validate_template(resolved))
    diagnostics.extend(diagnose_template_dependencies(resolved, registry))
    diagnostics.extend(diagnose_capability_requirements(resolved, provided=inherited_provides))
    return ResolvedTemplate(resolved, diagnostics, ancestry=ancestry)


def _compose(base: RumiTemplate | None, child: RumiTemplate) -> tuple[RumiTemplate, list[TemplateDiagnostic]]:
    if base is None:
        return deepcopy(child), []
    raw = base.to_dict()
    child_raw = child.to_dict()
    raw.update({key: value for key, value in child_raw.items() if key not in {"pieces", "capabilities"}})
    raw["capabilities"] = {
        "provides": sorted(set(base.capabilities.provides) | set(child.capabilities.provides)),
        "requires": sorted(set(base.capabilities.requires) | set(child.capabilities.requires)),
        "permissions": sorted(set(base.capabilities.permissions) | set(child.capabilities.permissions)),
    }
    pieces, diagnostics = merge_template_pieces(base.pieces, child.pieces, template_id=child.id)
    raw["pieces"] = [piece.to_dict() for piece in pieces]
    parsed = parse_template(raw, source_path=str(child.source_path) if child.source_path else None)
    diagnostics.extend(parsed.diagnostics)
    return parsed.template or child, diagnostics


def _extends_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _slot_insert_index(pieces: list[TemplatePiece], slot: str | None) -> int | None:
    if not slot:
        return None
    for index, piece in enumerate(pieces):
        if piece.id == slot or piece.slot == slot:
            return index + 1
    return None


def _order_pieces(pieces: list[TemplatePiece]) -> list[TemplatePiece]:
    indexed = list(enumerate(pieces))
    indexed.sort(key=lambda item: (item[1].order is None, item[1].order if item[1].order is not None else item[0], item[0]))
    return [piece for _, piece in indexed]


def _apply_patch(raw: dict[str, Any], patch: dict[str, Any], *, template_id: str, patch_index: int) -> TemplateDiagnostic | None:
    op = patch.get("op")
    path = patch.get("path")
    if op not in {"replace", "add", "remove"} or not isinstance(path, str) or not path.startswith("/"):
        return TemplateDiagnostic(
            code="template.patch.invalid",
            message="patch must contain op replace/add/remove and JSON pointer path",
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
        return current[int(token)]
    if isinstance(current, dict):
        return current[token]
    raise TypeError("pointer traversed a scalar value")


def _replace_value(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        parent[int(token)] = value
    else:
        if token not in parent:
            raise KeyError(token)
        parent[token] = value


def _add_value(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        if token == "-":
            parent.append(value)
        else:
            parent.insert(int(token), value)
    else:
        parent[token] = value


def _remove_value(parent: Any, token: str) -> None:
    if isinstance(parent, list):
        del parent[int(token)]
    else:
        del parent[token]


def _unescape_pointer(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")
