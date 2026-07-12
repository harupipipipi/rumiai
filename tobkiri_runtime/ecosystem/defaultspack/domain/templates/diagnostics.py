from __future__ import annotations

from .models import RumiTemplate, TemplateDiagnostic
from .registry import TemplateRegistry
from .resolver import diagnose_capability_requirements, diagnose_template_dependencies
from .validation import validate_template


def collect_template_diagnostics(
    template: RumiTemplate,
    *,
    registry: TemplateRegistry | None = None,
    provided_capabilities: set[str] | None = None,
) -> list[TemplateDiagnostic]:
    diagnostics = validate_template(template)
    if registry is not None:
        diagnostics.extend(diagnose_template_dependencies(template, registry))
    diagnostics.extend(diagnose_capability_requirements(template, provided=provided_capabilities))
    return diagnostics


def diagnostics_have_errors(diagnostics: list[TemplateDiagnostic]) -> bool:
    return any(diagnostic.is_error for diagnostic in diagnostics)
