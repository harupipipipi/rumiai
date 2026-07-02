from __future__ import annotations

from pathlib import PurePath, PurePosixPath, PureWindowsPath

from .models import RumiTemplate, TemplateDiagnostic, TemplatePiece, TemplateTrustLevel


_SHELL_HANDLER_NAMES = {
    "sh",
    "bash",
    "zsh",
    "fish",
    "cmd",
    "cmd.exe",
    "powershell",
    "pwsh",
    "shell",
    "subprocess",
}
_SHELL_TOKENS = ("&&", "||", ";", "|", "$(", "`", "\n", "\r")


def assess_template_security(template: RumiTemplate) -> list[TemplateDiagnostic]:
    trust_level = _trust_value(template.trust_level)
    if trust_level == TemplateTrustLevel.BUILTIN.value:
        return []

    diagnostics: list[TemplateDiagnostic] = []
    for piece in template.pieces:
        diagnostics.extend(_diagnose_piece_paths(template, piece))
        diagnostics.extend(_diagnose_shell_like_handlers(template, piece))
    return diagnostics


def is_safe_template(template: RumiTemplate) -> bool:
    return not any(diagnostic.is_error for diagnostic in assess_template_security(template))


def _diagnose_piece_paths(template: RumiTemplate, piece: TemplatePiece) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    for field_name, value in (("path", piece.path), ("entrypoint", piece.entrypoint)):
        if not value:
            continue
        if _is_absolute_path(value):
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.security.absolute_path",
                    message=f"{field_name} must be relative for non-builtin templates",
                    template_id=template.id,
                    piece_id=piece.id,
                    path=f"/pieces/{piece.id}/{field_name}",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
        if _contains_parent_traversal(value):
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.security.parent_traversal",
                    message=f"{field_name} must not contain '..' path segments",
                    template_id=template.id,
                    piece_id=piece.id,
                    path=f"/pieces/{piece.id}/{field_name}",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
    return diagnostics


def _diagnose_shell_like_handlers(
    template: RumiTemplate, piece: TemplatePiece
) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    for field_name, value in (("handler", piece.handler), ("entrypoint", piece.entrypoint)):
        if not value:
            continue
        normalized = value.strip().lower()
        first_word = normalized.split(" ", 1)[0]
        if (
            normalized.startswith("shell:")
            or first_word in _SHELL_HANDLER_NAMES
            or any(token in value for token in _SHELL_TOKENS)
        ):
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.security.shell_like_handler",
                    message=f"{field_name} must not invoke shell-like handlers for non-builtin templates",
                    template_id=template.id,
                    piece_id=piece.id,
                    path=f"/pieces/{piece.id}/{field_name}",
                    source_path=str(template.source_path) if template.source_path else None,
                )
            )
    return diagnostics


def _is_absolute_path(value: str) -> bool:
    return (
        PurePath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _contains_parent_traversal(value: str) -> bool:
    return ".." in PurePath(value).parts or ".." in PureWindowsPath(value).parts


def _trust_value(value: TemplateTrustLevel | str) -> str:
    return value.value if isinstance(value, TemplateTrustLevel) else str(value)
