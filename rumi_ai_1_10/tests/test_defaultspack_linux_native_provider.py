from __future__ import annotations

from collections.abc import Sequence

from ecosystem.defaultspack.backend.sandbox.models import (
    EnsureRuntimeRequest,
    ProviderInstance,
    RuntimeRequirements,
    UpdateRuntimeRequest,
)
from ecosystem.defaultspack.backend.sandbox.providers.base import NullProgressSink
from ecosystem.defaultspack.backend.sandbox.providers.linux_native import (
    DESKTOP_CAPABILITIES,
    LINUX_NATIVE_APT_PACKAGES,
    LinuxCommandResult,
    LinuxNativeProvider,
)


class FakeAptRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.installed = False

    def __call__(
        self,
        command: Sequence[str],
        input_text: str | None,
        timeout: float | None,
    ) -> LinuxCommandResult:
        cmd = list(command)
        self.calls.append((cmd, input_text, timeout))
        if cmd[-1:] == ["update"] and any(part.endswith("apt-get") for part in cmd):
            return LinuxCommandResult(returncode=0)
        if "install" in cmd and any(part.endswith("apt-get") for part in cmd):
            self.installed = True
            return LinuxCommandResult(returncode=0)
        return LinuxCommandResult(returncode=1, stderr=f"unexpected command: {cmd!r}")

    def command_containing(self, *parts: str) -> list[str]:
        for command, _input_text, _timeout in self.calls:
            if all(part in command for part in parts):
                return command
        raise AssertionError(f"command containing {parts!r} was not called")


class FakeLinuxNativeSession:
    def __init__(self, runner: FakeAptRunner) -> None:
        self._runner = runner

    def missing_commands(self) -> list[str]:
        if self._runner.installed:
            return []
        return ["Xvfb", "openbox", "xdotool", "import"]


def _persisted_ready_instance(metadata: dict[str, object]) -> ProviderInstance:
    return ProviderInstance(
        provider_id="linux_native",
        provider_instance_id="linux-native-seat-1",
        sandbox_id="seat-1",
        runtime_id="linux-native-x11",
        state="ready",
        opaque_state={"display": ":88", "x11_session": metadata, "startup_status": {"executed": True}},
        generation=3,
    )


def test_linux_native_ensure_installs_desktop_dependencies(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    monkeypatch.setattr(linux_native.sys, "platform", "linux")
    monkeypatch.setattr(linux_native.os, "geteuid", lambda: 0, raising=False)
    runner = FakeAptRunner()
    provider = LinuxNativeProvider(
        session_factory=lambda **_kwargs: FakeLinuxNativeSession(runner),
        runner=runner,
        apt_get_path="/usr/bin/apt-get",
    )
    requirements = RuntimeRequirements(required_capabilities=DESKTOP_CAPABILITIES)

    before = provider.doctor(requirements)
    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="linux_native", requirements=requirements), NullProgressSink())
    after = provider.doctor(requirements)

    assert before.ready is False
    assert "command:Xvfb" in before.missing_requirements
    assert ensured.ok is True
    assert after.ready is True
    assert runner.command_containing("/usr/bin/apt-get", "update")[-1] == "update"
    install = runner.command_containing("/usr/bin/apt-get", "install", "-y")
    assert {"xvfb", "openbox", "xdotool", "imagemagick"}.issubset(set(install))
    assert set(LINUX_NATIVE_APT_PACKAGES).issubset(set(install))


def test_linux_native_update_refreshes_desktop_dependencies(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    monkeypatch.setattr(linux_native.sys, "platform", "linux")
    monkeypatch.setattr(linux_native.os, "geteuid", lambda: 0, raising=False)
    runner = FakeAptRunner()
    runner.installed = True
    provider = LinuxNativeProvider(
        session_factory=lambda **_kwargs: FakeLinuxNativeSession(runner),
        runner=runner,
        apt_get_path="/usr/bin/apt-get",
    )

    updated = provider.update(UpdateRuntimeRequest(provider_id="linux_native"), NullProgressSink())

    assert updated.ok is True
    assert runner.command_containing("/usr/bin/apt-get", "update")[-1] == "update"
    assert runner.command_containing("/usr/bin/apt-get", "install", "-y")


def test_linux_native_ensure_does_not_install_unsupported_capabilities(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    monkeypatch.setattr(linux_native.sys, "platform", "linux")
    monkeypatch.setattr(linux_native.os, "geteuid", lambda: 0, raising=False)
    runner = FakeAptRunner()
    provider = LinuxNativeProvider(
        session_factory=lambda **_kwargs: FakeLinuxNativeSession(runner),
        runner=runner,
        apt_get_path="/usr/bin/apt-get",
    )
    requirements = RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec"}))

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="linux_native", requirements=requirements), NullProgressSink())

    assert ensured.ok is False
    assert runner.calls == []
    assert {diagnostic.code for diagnostic in ensured.diagnostics} >= {"LINUX_NATIVE_CAPABILITIES_UNSUPPORTED"}


def test_linux_native_ensure_fails_closed_when_apt_is_missing(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    monkeypatch.setattr(linux_native.sys, "platform", "linux")
    monkeypatch.setattr(linux_native.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(linux_native.shutil, "which", lambda _name: None)
    runner = FakeAptRunner()
    provider = LinuxNativeProvider(
        session_factory=lambda **_kwargs: FakeLinuxNativeSession(runner),
        runner=runner,
    )
    requirements = RuntimeRequirements(required_capabilities=DESKTOP_CAPABILITIES)

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="linux_native", requirements=requirements), NullProgressSink())

    assert ensured.ok is False
    assert runner.calls == []
    assert [diagnostic.code for diagnostic in ensured.diagnostics] == ["LINUX_NATIVE_PACKAGE_MANAGER_MISSING"]


def test_linux_native_reconcile_cleans_persisted_x11_session_before_stopping(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    metadata = {"display": ":88", "processes": {"xvfb": {"pid": 1001}}}
    cleanup_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        linux_native,
        "_cleanup_owned_x11_session",
        lambda value: cleanup_calls.append(dict(value)) or {"cleaned": True},
    )
    provider = LinuxNativeProvider()
    persisted = _persisted_ready_instance(metadata)

    result = provider.reconcile(persisted)

    assert cleanup_calls == [metadata]
    assert result.changed is True
    assert result.instance.state == "stopped"
    assert result.instance.generation == persisted.generation + 1
    assert "display" not in result.instance.opaque_state
    assert "x11_session" not in result.instance.opaque_state
    assert "startup_status" not in result.instance.opaque_state


def test_linux_native_stop_and_destroy_cleanup_missing_in_memory_session(monkeypatch) -> None:
    import ecosystem.defaultspack.backend.sandbox.providers.linux_native as linux_native

    metadata = {"display": ":89", "processes": {"openbox": {"pid": 1002}, "xvfb": {"pid": 1003}}}
    cleanup_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        linux_native,
        "_cleanup_owned_x11_session",
        lambda value: cleanup_calls.append(dict(value)) or {"cleaned": True},
    )
    provider = LinuxNativeProvider()
    persisted = _persisted_ready_instance(metadata)

    provider.stop(persisted)
    stopped = provider._instances[persisted.provider_instance_id]
    provider.destroy(persisted)

    assert cleanup_calls == [metadata, metadata]
    assert stopped.state == "stopped"
    assert "x11_session" not in stopped.opaque_state
