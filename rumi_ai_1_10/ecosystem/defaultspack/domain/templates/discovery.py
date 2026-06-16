from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import RumiTemplate, TemplateDiagnostic, TemplateTrustLevel
from .validation import parse_template


@dataclass
class TemplateDiscoveryResult:
    templates: list[RumiTemplate] = field(default_factory=list)
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(diagnostic.is_error for diagnostic in self.diagnostics)


def default_template_roots(defaultspack_root: str | Path | None = None) -> list[Path]:
    root = Path(defaultspack_root) if defaultspack_root is not None else Path(__file__).resolve().parents[2]
    return [root / "templates", root / "user_data" / "shared" / "templates"]


def discover_templates(
    roots: list[str | Path] | None = None,
    *,
    defaultspack_root: str | Path | None = None,
    trust_level: TemplateTrustLevel | str | None = None,
) -> TemplateDiscoveryResult:
    search_roots = [Path(root) for root in roots] if roots is not None else default_template_roots(defaultspack_root)
    result = TemplateDiscoveryResult()
    for root in search_roots:
        for template_path in _iter_template_files(root):
            loaded = load_template_file(template_path, trust_level=trust_level)
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

    parsed = parse_template(
        raw,
        source_path=str(path),
        trust_level=str(trust_level.value if isinstance(trust_level, TemplateTrustLevel) else trust_level)
        if trust_level is not None
        else None,
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
