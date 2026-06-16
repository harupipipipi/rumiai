from __future__ import annotations

from .diagnostics import collect_template_diagnostics, diagnostics_have_errors
from .discovery import TemplateDiscoveryResult, default_template_roots, discover_templates, load_template_file
from .migration import migrate_template_dict, register_template_migrations
from .models import (
    ResolvedTemplate,
    RumiTemplate,
    TemplateCapabilitySpec,
    TemplateContext,
    TemplateDiagnostic,
    TemplateKind,
    TemplatePiece,
    TemplatePieceKind,
    TemplateStatus,
    TemplateTrustLevel,
)
from .registry import TemplateRegistry, build_template_registry
from .resolver import (
    apply_template_patches,
    diagnose_capability_requirements,
    diagnose_template_dependencies,
    merge_template_pieces,
    resolve_template,
)
from .security import assess_template_security, is_safe_template
from .validation import TemplateValidationResult, has_errors, parse_template, validate_template
from .projectors import build_template_catalog, project_resolved_templates

__all__ = [
    "ResolvedTemplate",
    "RumiTemplate",
    "TemplateCapabilitySpec",
    "TemplateContext",
    "TemplateDiagnostic",
    "TemplateDiscoveryResult",
    "TemplateKind",
    "TemplatePiece",
    "TemplatePieceKind",
    "TemplateRegistry",
    "TemplateStatus",
    "TemplateTrustLevel",
    "TemplateValidationResult",
    "apply_template_patches",
    "assess_template_security",
    "build_template_registry",
    "build_template_catalog",
    "collect_template_diagnostics",
    "default_template_roots",
    "diagnose_capability_requirements",
    "diagnose_template_dependencies",
    "diagnostics_have_errors",
    "discover_templates",
    "has_errors",
    "is_safe_template",
    "load_template_file",
    "merge_template_pieces",
    "migrate_template_dict",
    "parse_template",
    "project_resolved_templates",
    "register_template_migrations",
    "resolve_template",
    "validate_template",
]
