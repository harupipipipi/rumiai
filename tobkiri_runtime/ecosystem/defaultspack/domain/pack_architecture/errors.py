"""Errors raised by the defaultspack Base/Shell composition layer."""

from __future__ import annotations


class PackArchitectureError(ValueError):
    """Base error for malformed or unsafe architecture inputs."""


class CatalogError(PackArchitectureError):
    """Raised when a pack catalog cannot be loaded or is inconsistent."""


class ProfileResolutionError(PackArchitectureError):
    """Raised when a profile cannot be resolved fail-closed."""


class LegacyMigrationError(PackArchitectureError):
    """Raised when a legacy profile cannot be migrated safely."""
