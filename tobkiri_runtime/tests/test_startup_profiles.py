"""Pack v4 replacement for legacy StartupProfileManager tests."""

from tests.legacy_authority_contracts import (
    assert_profile_resolver_requires_authority_snapshot,
    assert_retired_module_absent,
)


def test_legacy_startup_profile_registry_is_absent() -> None:
    """Startup profiles are resolved from finite v4 records."""
    assert_retired_module_absent("core_runtime.interface_registry")


def test_startup_profile_requires_authority_snapshot() -> None:
    """An unresolved v4 startup profile fails closed."""
    assert_profile_resolver_requires_authority_snapshot()
