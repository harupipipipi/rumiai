from __future__ import annotations

import importlib.util
import json
import plistlib
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tobkiri_launcher/scripts/verify_macos_launcher_cold_boot.py"
WORKFLOW = ROOT / ".github/workflows/desktop-installers.yml"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "verify_macos_launcher_cold_boot",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_script()


@dataclass
class _Clock:
    value: float = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _Process:
    pid = 4242
    stdout = None

    def poll(self) -> None:
        return None


def _bundle_and_config(tmp_path: Path) -> tuple[object, Path]:
    app_bundle = tmp_path / VERIFY.CI_APP_NAME
    executable = app_bundle / VERIFY.EXECUTABLE_RELATIVE
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    info_plist = app_bundle / VERIFY.INFO_PLIST_RELATIVE
    info_plist.parent.mkdir(exist_ok=True)
    with info_plist.open("wb") as output:
        plistlib.dump({"CFBundleIdentifier": VERIFY.CI_BUNDLE_IDENTIFIER}, output)

    app_data_parent = tmp_path / "Application Support"
    app_data_parent.mkdir()
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    config = VERIFY.ColdBootConfig(
        app_bundle=app_bundle,
        app_data_dir=app_data_parent / VERIFY.CI_APP_DATA_DIRECTORY_NAME,
        diagnostics_dir=diagnostics,
        kernel_port=18765,
        timeout_seconds=5.0,
    )
    return config, diagnostics


def _write_embedded_broker_connection(app_data_dir: Path, broker_port: int) -> None:
    connection = app_data_dir / VERIFY.BROKER_CONNECTION_RELATIVE
    connection.parent.mkdir(parents=True)
    connection.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": broker_port,
                "pid": _Process.pid,
                "token": "not-printed-test-token",
            }
        ),
        encoding="utf-8",
    )
    connection.chmod(0o600)


def _probes(
    clock: _Clock,
    request: Callable[[int, str], Optional[object]],
    parent_pid: Callable[[int], Optional[int]],
    signals: list[tuple[int, signal.Signals]],
) -> object:
    return VERIFY.ColdBootProbes(
        port_available=lambda _port: True,
        reserve_broker_port=lambda _kernel_port: 18770,
        http_get=request,
        listener_pid=lambda _port: 4243,
        parent_pid=parent_pid,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        kill_process_group=lambda process_group, sent: signals.append(
            (process_group, sent)
        ),
    )


def test_cold_boot_requires_embedded_broker_then_owned_kernel_and_panel(
    tmp_path: Path,
) -> None:
    config, _diagnostics = _bundle_and_config(tmp_path)
    clock = _Clock()
    signals: list[tuple[int, signal.Signals]] = []
    calls: list[tuple[int, str]] = []
    launched_environment: dict[str, str] = {}

    def request(port: int, path: str) -> Optional[object]:
        calls.append((port, path))
        if port == 18770 and path == VERIFY.BROKER_HEALTH_PATH:
            _write_embedded_broker_connection(config.app_data_dir, port)
            return VERIFY.HttpResponse(
                200,
                {"content-type": "application/json"},
                b'{"ok":true,"status":"running"}',
            )
        if port == config.kernel_port and path == VERIFY.KERNEL_HEALTH_PATH:
            return VERIFY.HttpResponse(
                200,
                {"content-type": "application/json"},
                b'{"success":true,"data":{"panel_ready":true}}',
            )
        if port == config.kernel_port and path == VERIFY.PANEL_BOOTSTRAP_PATH:
            return VERIFY.HttpResponse(
                200,
                {"content-type": "text/html; charset=utf-8"},
                b'<html><script src="/panel/assets/index-test.js"></script></html>',
            )
        return None

    def launch(_executable: Path, _bundle: Path, environment: object) -> _Process:
        launched_environment.update(environment)
        return _Process()

    result = VERIFY.verify_cold_boot(
        config,
        probes=_probes(
            clock,
            request,
            lambda process_id: 4242 if process_id == 4243 else 1,
            signals,
        ),
        launch=launch,
        base_environment={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "CI_TEST_SECRET": "must-not-reach-app",
        },
    )

    assert result.kernel_pid == 4243
    assert result.panel_reachable is True
    assert calls == [
        (18770, VERIFY.BROKER_HEALTH_PATH),
        (config.kernel_port, VERIFY.KERNEL_HEALTH_PATH),
        (config.kernel_port, VERIFY.PANEL_BOOTSTRAP_PATH),
    ]
    assert launched_environment["RUMI_VIEWER_BROKER_PORT"] == "18770"
    assert launched_environment["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert launched_environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert "CI_TEST_SECRET" not in launched_environment
    assert signals == [
        (4242, signal.SIGTERM),
        (4242, signal.SIGKILL),
    ]


def test_cold_boot_rejects_healthy_kernel_not_owned_by_launched_app(
    tmp_path: Path,
) -> None:
    config, diagnostics = _bundle_and_config(tmp_path)
    clock = _Clock()
    signals: list[tuple[int, signal.Signals]] = []

    def request(port: int, path: str) -> Optional[object]:
        if port == 18770 and path == VERIFY.BROKER_HEALTH_PATH:
            _write_embedded_broker_connection(config.app_data_dir, port)
            return VERIFY.HttpResponse(200, {}, b'{"ok":true,"status":"running"}')
        if port == config.kernel_port and path == VERIFY.KERNEL_HEALTH_PATH:
            return VERIFY.HttpResponse(
                200,
                {},
                b'{"success":true,"data":{"panel_ready":true}}',
            )
        return None

    with pytest.raises(VERIFY.ColdBootError, match="not owned"):
        VERIFY.verify_cold_boot(
            config,
            probes=_probes(clock, request, lambda _process_id: 1, signals),
            launch=lambda *_args: _Process(),
            base_environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        )

    diagnostic = json.loads(
        (diagnostics / VERIFY.DIAGNOSTIC_FILENAME).read_text(encoding="utf-8")
    )
    assert diagnostic["status"] == "failed"
    assert "not-printed-test-token" not in json.dumps(diagnostic)
    assert signals == [
        (4242, signal.SIGTERM),
        (4242, signal.SIGKILL),
    ]


def test_cold_boot_fails_closed_when_ci_app_data_is_not_fresh(tmp_path: Path) -> None:
    config, _diagnostics = _bundle_and_config(tmp_path)
    config.app_data_dir.mkdir()
    launched = False

    def launch(*_args: object) -> _Process:
        nonlocal launched
        launched = True
        return _Process()

    with pytest.raises(VERIFY.ColdBootError, match="must be fresh"):
        VERIFY.verify_cold_boot(
            config,
            launch=launch,
            base_environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        )

    assert launched is False


def test_workflow_runs_cold_boot_after_host_seal_and_before_dmg() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    host_seal = workflow.index("Host-seal and launch-test packaged Python")
    cold_boot = workflow.index("Cold-boot packaged macOS CI/E2E Launcher")
    dmg = workflow.index("Build macOS DMG installer")

    assert host_seal < cold_boot < dmg
    assert "verify_macos_launcher_cold_boot.py" in workflow
    assert "--kernel-port 8765" in workflow
    assert "--timeout-seconds 180" in workflow
    assert "launcher-cold-boot.v1.json" in workflow
