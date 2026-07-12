from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import CURRENT_TEMPLATE_SCHEMA_VERSION, TemplateDiagnostic


TemplateMigration = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class TemplateMigrationResult:
    document: dict[str, Any]
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)


class TemplateMigrationRegistry:
    def __init__(self) -> None:
        self._migrations: dict[tuple[int, int], TemplateMigration] = {}

    def register(
        self,
        from_version: int,
        to_version: int,
        migration: TemplateMigration,
    ) -> None:
        if to_version != from_version + 1:
            raise ValueError("template migrations must advance by one schema version")
        self._migrations[(from_version, to_version)] = migration

    def migrate(
        self,
        raw: dict[str, Any],
        target_version: int = CURRENT_TEMPLATE_SCHEMA_VERSION,
    ) -> TemplateMigrationResult:
        document = deepcopy(raw)
        diagnostics: list[TemplateDiagnostic] = []
        current_version = _schema_version(document)
        if current_version > target_version:
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.migration.future_schema_version",
                    message="template schema_version is newer than this runtime; downgrade is not allowed",
                    template_id=_template_id(document),
                    severity="error",
                    path="/schema_version",
                )
            )
            return TemplateMigrationResult(document=document, diagnostics=diagnostics)
        if current_version == target_version:
            return TemplateMigrationResult(document=document, diagnostics=diagnostics)
        while current_version < target_version:
            next_version = current_version + 1
            migration = self._migrations.get((current_version, next_version))
            if migration is None:
                diagnostics.append(
                    TemplateDiagnostic(
                        code="template.migration.missing",
                        message=(
                            f"no data migration registered for schema {current_version}"
                            f" -> {next_version}"
                        ),
                        template_id=_template_id(document),
                        path="/schema_version",
                    )
                )
                return TemplateMigrationResult(document=document, diagnostics=diagnostics)
            document = migration(deepcopy(document))
            current_version = next_version
            diagnostics.append(
                TemplateDiagnostic(
                    code="template.migration.applied",
                    message=f"template document migrated to schema_version {current_version}",
                    template_id=_template_id(document),
                    severity="info",
                    path="/schema_version",
                )
            )
        return TemplateMigrationResult(document=document, diagnostics=diagnostics)


def migrate_template_dict(
    raw: dict[str, Any],
    *,
    target_version: int | str | None = None,
) -> tuple[dict[str, Any], list[TemplateDiagnostic]]:
    registry = register_template_migrations()
    target = _coerce_target_version(target_version)
    result = registry.migrate(raw, target_version=target)
    return result.document, result.diagnostics


def register_template_migrations() -> TemplateMigrationRegistry:
    registry = TemplateMigrationRegistry()
    registry.register(0, 1, _migrate_v0_to_v1)
    return registry


def _migrate_v0_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(raw)
    migrated.setdefault("schema_version", 1)
    _copy_alias(migrated, "template_version", "version")
    _copy_alias(migrated, "template_status", "status")
    _copy_alias(migrated, "template_pieces", "pieces")
    _copy_alias(migrated, "schemaVersion", "schema_version")
    return migrated


def _copy_alias(document: dict[str, Any], alias: str, canonical: str) -> None:
    if canonical not in document and alias in document:
        document[canonical] = deepcopy(document[alias])


def _schema_version(document: dict[str, Any]) -> int:
    value = document.get("schema_version")
    if value is None:
        return 0
    if isinstance(value, bool):
        return CURRENT_TEMPLATE_SCHEMA_VERSION + 1
    try:
        return int(value)
    except (TypeError, ValueError):
        return CURRENT_TEMPLATE_SCHEMA_VERSION + 1


def _template_id(document: dict[str, Any]) -> str | None:
    value = document.get("id")
    return str(value) if value is not None else None


def _coerce_target_version(value: int | str | None) -> int:
    if value is None:
        return CURRENT_TEMPLATE_SCHEMA_VERSION
    try:
        return int(value)
    except (TypeError, ValueError):
        return CURRENT_TEMPLATE_SCHEMA_VERSION
