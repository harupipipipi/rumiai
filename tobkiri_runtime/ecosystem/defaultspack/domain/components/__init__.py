from __future__ import annotations

from .discovery import ComponentDiscoveryIssue, ComponentDiscoveryResult, discover_components
from .manifest import DomainComponent
from .registry import DomainComponentRegistry, get_domain_component_registry
from .validation import ComponentManifestError, validate_component_manifest

__all__ = [
    "ComponentDiscoveryIssue",
    "ComponentDiscoveryResult",
    "ComponentManifestError",
    "DomainComponent",
    "DomainComponentRegistry",
    "discover_components",
    "get_domain_component_registry",
    "validate_component_manifest",
]
