from __future__ import annotations

from collections.abc import Sequence

from ecosystem.defaultspack.backend.sandbox.models import (
    EnsureRuntimeRequest,
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
