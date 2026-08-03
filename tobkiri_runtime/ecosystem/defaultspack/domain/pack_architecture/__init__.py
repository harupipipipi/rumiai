"""Defaultspack-owned implementation of the ADR-016 composition boundary."""

from .catalog import DEFAULT_ASSETS_ROOT, PackCatalog
from .errors import (
    CatalogError,
    LegacyMigrationError,
    PackArchitectureError,
    ProfileResolutionError,
)
from .materializer import materialize_selected_artifacts
from .migration import migrate_legacy_profile, migrate_legacy_profile_file
from .model import (
    APP_SHELL_CONTRACT,
    PACK_SCHEMA,
    PROFILE_SCHEMA,
    ArtifactVariant,
    PackDefinition,
    PresentationContribution,
)
from .resolver import ResolvedProfile, SelectedArtifact, load_profile_document, resolve_profile

__all__ = [
    "APP_SHELL_CONTRACT",
    "PACK_SCHEMA",
    "PROFILE_SCHEMA",
    "ArtifactVariant",
    "CatalogError",
    "DEFAULT_ASSETS_ROOT",
    "LegacyMigrationError",
    "PackArchitectureError",
    "PackCatalog",
    "PackDefinition",
    "PresentationContribution",
    "ProfileResolutionError",
    "ResolvedProfile",
    "SelectedArtifact",
    "load_profile_document",
    "materialize_selected_artifacts",
    "migrate_legacy_profile",
    "migrate_legacy_profile_file",
    "resolve_profile",
]
