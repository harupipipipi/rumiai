"""Defaultspack's fail-closed Protocol v4 composition boundary."""

from .service import (
    ActivationStore,
    BundleIntegrityError,
    BundledCatalog,
    DefaultProfileV4Error,
    ProfileResolutionDenied,
    ResolvedDefaultProfile,
    resolve_default_profile,
)

__all__ = [
    "ActivationStore",
    "BundleIntegrityError",
    "BundledCatalog",
    "DefaultProfileV4Error",
    "ProfileResolutionDenied",
    "ResolvedDefaultProfile",
    "resolve_default_profile",
]
