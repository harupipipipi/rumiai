from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import RumiTemplate, TemplateDiagnostic, TemplateTrustLevel
from .validation import parse_template


@dataclass(frozen=True)
class TemplateRoot:
    path: Path
    trust_level: TemplateTrustLevel | str


@dataclass
class TemplateDiscoveryResult:
    templates: list[RumiTemplate] = field(default_factory=list)
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(diagnostic.is_error for diagnostic in self.diagnostics)


def default_template_roots(defaultspack_root: str | Path | None = None) -> list[TemplateRoot]:
    root = Path(defaultspack_root) if defaultspack_root is not None else Path(__file__).resolve().parents[2]
    return [
        TemplateRoot(root / "templates", TemplateTrustLevel.BUILTIN),
        TemplateRoot(root / "user_data" / "shared" / "templates", TemplateTrustLevel.USER),
    ]


def discover_templates(
    roots: list[str | Path | TemplateRoot] | None = None,
    *,
    defaultspack_root: str | Path | None = None,
    trust_level: TemplateTrustLevel | str | None = None,
) -> TemplateDiscoveryResult:
    search_roots = _normalize_roots(roots, defaultspack_root=defaultspack_root, trust_level=trust_level)
    result = TemplateDiscoveryResult()
    for template_root in search_roots:
        root_trust = _coerce_trust(template_root.trust_level)
        for template_path in _iter_template_files(template_root.path):
            loaded = load_template_file(template_path, trust_level=root_trust)
            result.diagnostics.extend(loaded.diagnostics)
            result.templates.extend(loaded.templates)
    return result


def load_template_file(
    template_path: str | Path,
    *,
    trust_level: TemplateTrustLevel | str | None = None,
) -> TemplateDiscoveryResult:
    path = Path(template_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return TemplateDiscoveryResult(
            diagnostics=[
                TemplateDiagnostic(
                    code="template.discovery.json_parse_error",
                    message=f"failed to parse template JSON: {exc.msg}",
                    path=f"line {exc.lineno}, column {exc.colno}",
                    source_path=str(path),
                )
            ]
        )
    except OSError as exc:
        return TemplateDiscoveryResult(
            diagnostics=[
                TemplateDiagnostic(
                    code="template.discovery.read_error",
                    message=f"failed to read template JSON: {exc}",
                    source_path=str(path),
                )
            ]
        )

    # Trust is assigned by the loader based on where the template came from.
    # Do not let a user-writable template self-declare ``trust_level: builtin``
    # and bypass path / shell diagnostics. Direct parse_template() remains a
    # lower-level parser for tests and in-memory builtin construction.
    effective_trust = _coerce_trust(trust_level) if trust_level is not None else _infer_file_trust(path)
    parsed = parse_template(
        raw,
        source_path=str(path),
        trust_level=effective_trust.value,
    )
    return TemplateDiscoveryResult(
        templates=[parsed.template] if parsed.template is not None else [],
        diagnostics=parsed.diagnostics,
    )


def _iter_template_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.name == "template.json" else []
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("template.json") if path.is_file())


def _normalize_roots(
    roots: list[str | Path | TemplateRoot] | None,
    *,
    defaultspack_root: str | Path | None,
    trust_level: TemplateTrustLevel | str | None,
) -> list[TemplateRoot]:
    if roots is None:
        configured_roots = default_template_roots(defaultspack_root)
    else:
        configured_roots = [
            root if isinstance(root, TemplateRoot) else TemplateRoot(Path(root), _infer_root_trust(Path(root), defaultspack_root))
            for root in roots
        ]
    if trust_level is None:
        return configured_roots
    forced_trust = _coerce_trust(trust_level)
    return [TemplateRoot(root.path, forced_trust) for root in configured_roots]


def _coerce_trust(value: TemplateTrustLevel | str) -> TemplateTrustLevel:
    if isinstance(value, TemplateTrustLevel):
        return value
    try:
        return TemplateTrustLevel(str(value))
    except ValueError:
        return TemplateTrustLevel.USER


def _infer_root_trust(root: Path, defaultspack_root: str | Path | None) -> TemplateTrustLevel:
    if defaultspack_root is not None:
        pack_root = Path(defaultspack_root)
        if _is_relative_to(root, pack_root / "templates"):
            return TemplateTrustLevel.BUILTIN
        if _is_relative_to(root, pack_root / "user_data" / "shared" / "templates"):
            return TemplateTrustLevel.USER
    return _infer_file_trust(root)


def _infer_file_trust(path: Path) -> TemplateTrustLevel:
    parts = path.parts
    for index, part in enumerate(parts):
        if part != "user_data":
            continue
        if parts[index:index + 3] == ("user_data", "shared", "templates"):
            return TemplateTrustLevel.USER
    for index, part in enumerate(parts):
        if part != "defaultspack":
            continue
        if len(parts) > index + 1 and parts[index + 1] == "templates":
            return TemplateTrustLevel.BUILTIN
    return TemplateTrustLevel.USER


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False
