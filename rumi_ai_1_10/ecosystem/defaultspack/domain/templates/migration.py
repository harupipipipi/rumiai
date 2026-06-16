from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import TemplateDiagnostic


def migrate_template_dict(
    raw: dict[str, Any],
    *,
    target_version: str | None = None,
) -> tuple[dict[str, Any], list[TemplateDiagnostic]]:
    migrated = deepcopy(raw)
    diagnostics: list[TemplateDiagnostic] = []
    if target_version is not None and migrated.get("version") != target_version:
        diagnostics.append(
            TemplateDiagnostic(
                code="template.migration.noop",
                message="no template migrations are registered; document was left unchanged",
                severity="info",
                template_id=str(migrated.get("id")) if migrated.get("id") is not None else None,
                path="/version",
            )
        )
    return migrated, diagnostics


def register_template_migrations() -> dict[str, object]:
    return {}
