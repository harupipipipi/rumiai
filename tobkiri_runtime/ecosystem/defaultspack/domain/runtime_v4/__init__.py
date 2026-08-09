"""Defaultspack's fail-closed Protocol v4 composition boundary."""

from .service import (
    ActiveDefaultProfile,
    ActivationStore,
    BundleIntegrityError,
    BundledCatalog,
    DefaultProfileV4Error,
    ProfileResolutionDenied,
    ResolvedDefaultProfile,
    dynamic_profile_edges,
    resolve_default_profile,
)

__all__ = [
    "ActiveDefaultProfile",
    "ActivationStore",
    "BundleIntegrityError",
    "BundledCatalog",
    "DefaultProfileV4Error",
    "ProfileResolutionDenied",
    "ResolvedDefaultProfile",
    "dynamic_profile_edges",
    "resolve_default_profile",
]
