"""Regression tests for the explicit application Profile composition root."""

from __future__ import annotations

import importlib

import pytest


def test_runtime_v4_import_does_not_install_profile_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sealed catalog package remains importable without Host modules."""

    import core_runtime.profile_runtime_port as profile_port
    import ecosystem.defaultspack.domain.runtime_v4 as runtime_v4

    monkeypatch.setattr(profile_port, "_PROFILE_RUNTIME", None)
    importlib.reload(runtime_v4)

    with pytest.raises(profile_port.ProfileRuntimeUnavailable):
        profile_port.require_profile_runtime()


def test_defaultspack_application_composition_installs_profile_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the application composition root supplies Defaultspack records."""

    import core_runtime.profile_runtime_port as profile_port
    from ecosystem.defaultspack.defaultspack.runtime_composition import (
        create_defaultspack_kernel,
    )

    monkeypatch.setattr(profile_port, "_PROFILE_RUNTIME", None)
    kernel = create_defaultspack_kernel()
    try:
        assert profile_port.require_profile_runtime().bootstrap_profile_id() == "defaults"
    finally:
        kernel.shutdown()


def test_profile_port_rejects_replacement_after_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later application cannot replace the captured Profile authority port."""

    import core_runtime.profile_runtime_port as profile_port
    from ecosystem.defaultspack.defaultspack.profile_runtime_composition import (
        install_defaultspack_profile_runtime,
    )

    monkeypatch.setattr(profile_port, "_PROFILE_RUNTIME", None)
    first = install_defaultspack_profile_runtime()
    assert install_defaultspack_profile_runtime() is first
    with pytest.raises(profile_port.ProfileRuntimeAlreadyConfigured):
        profile_port.register_profile_runtime(object())
    assert profile_port.require_profile_runtime() is first
