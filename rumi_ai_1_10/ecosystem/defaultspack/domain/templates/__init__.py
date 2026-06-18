from __future__ import annotations

from .activation import TemplateActivationPlan, TemplateActivationPlanner, TemplateActivationState
from .diagnostics import collect_template_diagnostics, diagnostics_have_errors
from .discovery import (
    TemplateDiscoveryResult,
    TemplateRoot,
    default_template_roots,
    discover_templates,
    load_template_file,
)
from .migration import migrate_template_dict, register_template_migrations
from .models import (
    CURRENT_TEMPLATE_SCHEMA_VERSION,
    ResolvedTemplate,
    RumiTemplate,
    TemplateCapabilitySpec,
    TemplateContext,
    TemplateDependencySpec,
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
from .projectors import (
    build_template_catalog,
    empty_template_catalog,
    merge_settings_sections,
    project_resolved_templates,
)

__all__ = [
    "ResolvedTemplate",
    "CURRENT_TEMPLATE_SCHEMA_VERSION",
    "RumiTemplate",
    "TemplateActivationPlan",
    "TemplateActivationPlanner",
    "TemplateActivationState",
    "TemplateCapabilitySpec",
    "TemplateContext",
    "TemplateDependencySpec",
    "TemplateDiagnostic",
    "TemplateDiscoveryResult",
    "TemplateKind",
    "TemplatePiece",
    "TemplatePieceKind",
    "TemplateRegistry",
    "TemplateRoot",
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
    "empty_template_catalog",
    "has_errors",
    "is_safe_template",
    "load_template_file",
    "merge_settings_sections",
    "merge_template_pieces",
    "migrate_template_dict",
    "parse_template",
    "project_resolved_templates",
    "register_template_migrations",
    "resolve_template",
    "validate_template",
]
