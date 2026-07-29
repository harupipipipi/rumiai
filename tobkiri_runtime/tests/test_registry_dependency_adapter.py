from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend_core.ecosystem.registry import ComponentInfo, PackInfo, resolve_load_order
from core_runtime.dependency_resolver import (
    CircularDependencyError,
    MissingDependencyError,
    VersionMismatchError,
)


def _pack(
    pack_id: str,
    *,
    dependencies: object | None = None,
    depends_on: object | None = None,
    version: str = "1.0.0",
    components: dict[str, ComponentInfo] | None = None,
) -> PackInfo:
    """Build a minimal registry PackInfo for resolver adapter tests."""
    ecosystem: dict[str, object] = {"pack_id": pack_id}
    if dependencies is not None:
        ecosystem["dependencies"] = dependencies
    if depends_on is not None:
        ecosystem["depends_on"] = depends_on
    return PackInfo(
        pack_id=pack_id,
        pack_identity=f"test:{pack_id}",
        version=version,
        uuid="00000000-0000-0000-0000-000000000001",
        ecosystem=ecosystem,
        path=Path("/tmp") / pack_id,
        components=components or {},
    )


def test_registry_resolver_delegates_pack_dependencies_to_canonical_resolver():
    packs = {
        "consumer": _pack(
            "consumer",
            depends_on=[{"pack_id": "provider", "version": ">=1.0,<2.0"}],
        ),
        "provider": _pack("provider", version="1.5.0"),
    }

    assert resolve_load_order(packs) == ["provider", "consumer"]


def test_registry_resolver_fails_closed_for_missing_dependencies():
    packs = {"consumer": _pack("consumer", dependencies={"missing": ">=1.0"})}

    with pytest.raises(MissingDependencyError):
        resolve_load_order(packs)


def test_registry_resolver_fails_closed_for_version_mismatches():
    packs = {
        "consumer": _pack("consumer", dependencies={"provider": ">=2.0"}),
        "provider": _pack("provider", version="1.9.9"),
    }

    with pytest.raises(VersionMismatchError):
        resolve_load_order(packs)


def test_registry_resolver_adapts_component_connectivity_dependencies():
    provider_component = ComponentInfo(
        type="provider",
        id="provider_component",
        version="1.0.0",
        uuid="00000000-0000-0000-0000-000000000002",
        manifest={"connectivity": {"provides": ["test.capability"]}},
        path=Path("/tmp/provider_component"),
        pack_id="provider",
    )
    consumer_component = ComponentInfo(
        type="consumer",
        id="consumer_component",
        version="1.0.0",
        uuid="00000000-0000-0000-0000-000000000003",
        manifest={"connectivity": {"requires": ["test.capability"]}},
        path=Path("/tmp/consumer_component"),
        pack_id="consumer",
    )
    packs = {
        "consumer": _pack("consumer", components={"consumer": consumer_component}),
        "provider": _pack("provider", components={"provider": provider_component}),
    }

    assert resolve_load_order(packs) == ["provider", "consumer"]


def test_registry_resolver_fails_closed_for_cycles():
    packs = {
        "first": _pack("first", dependencies={"second": ">=1.0"}),
        "second": _pack("second", dependencies={"first": ">=1.0"}),
    }

    with pytest.raises(CircularDependencyError):
        resolve_load_order(packs)
