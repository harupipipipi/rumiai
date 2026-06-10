from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core_runtime.di_container import reset_container, get_container
from core_runtime.provider_secure_executor import ProviderAwareSecureExecutor
from core_runtime.sandbox_provider import (
    ProviderSandboxManager,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxProviderCapabilities,
    build_execution_request_from_file,
)


class FakeSandboxProvider:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.requests: list[SandboxExecutionRequest] = []

    def provider_id(self) -> str:
        return "fake"

    def capabilities(self) -> SandboxProviderCapabilities:
        return SandboxProviderCapabilities(
            provider_id="fake",
            execution=True,
            browser=True,
            desktop=True,
            live_view=True,
            recording=True,
        )

    def is_available(self) -> bool:
        return self.available

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        self.requests.append(request)
        return SandboxExecutionResult(
            success=True,
            output={"ran": request.entrypoint, "phase": request.phase},
            execution_mode="sandbox:fake",
            execution_time_ms=12.5,
            provider_id="fake",
            session_id="sess_123",
            live_view_url="https://sandbox.example/live/sess_123",
            replay_url="https://sandbox.example/replay/sess_123",
        )


def test_build_execution_request_limits_files_to_entrypoint(tmp_path: Path) -> None:
    component_dir = tmp_path / "component"
    component_dir.mkdir()
    entrypoint = component_dir / "main.py"
    entrypoint.write_text("def run(ctx): return {'ok': True}\n", encoding="utf-8")
    ignored = component_dir / "ignored.py"
    ignored.write_text("raise RuntimeError('should not be sent')\n", encoding="utf-8")

    request = build_execution_request_from_file(
        pack_id="pack",
        component_id="component",
        phase="run",
        file_path=entrypoint,
        component_dir=component_dir,
        context={"payload": {"x": 1}},
        timeout=30,
    )

    assert request.entrypoint == "main.py"
    assert list(request.source_files) == ["main.py"]
    assert "ignored.py" not in request.source_files
    assert request.context == {"payload": {"x": 1}}


def test_strict_mode_uses_provider_when_docker_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
    fake_provider = FakeSandboxProvider()
    manager = ProviderSandboxManager([fake_provider])
    executor = ProviderAwareSecureExecutor(provider_sandbox_manager=manager)
    monkeypatch.setattr(executor, "is_docker_available", lambda: False)

    component_dir = tmp_path / "component"
    component_dir.mkdir()
    entrypoint = component_dir / "main.py"
    entrypoint.write_text("def run(ctx): return {'ok': True}\n", encoding="utf-8")

    result = executor.execute_component_phase(
        pack_id="pack",
        component_id="component",
        phase="run",
        file_path=entrypoint,
        component_dir=component_dir,
        context={"phase": "run", "payload": {"safe": True}, "unsafe": "drop"},
        timeout=30,
    )

    assert result.success
    assert result.execution_mode == "sandbox:fake"
    assert result.output == {"ran": "main.py", "phase": "run"}
    assert "sandbox_provider=fake" in result.warnings
    assert "sandbox_session=sess_123" in result.warnings
    assert fake_provider.requests[0].context == {"phase": "run", "payload": {"safe": True}}


def test_strict_mode_rejects_when_no_provider_or_docker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
    executor = ProviderAwareSecureExecutor(provider_sandbox_manager=ProviderSandboxManager([]))
    monkeypatch.setattr(executor, "is_docker_available", lambda: False)

    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("def run(ctx): return {'ok': True}\n", encoding="utf-8")

    result = executor.execute_component_phase(
        pack_id="pack",
        component_id="component",
        phase="run",
        file_path=entrypoint,
        context={"payload": {"safe": True}},
        timeout=30,
    )

    assert not result.success
    assert result.error_type == "sandbox_provider_or_docker_required"
    assert result.execution_mode == "rejected"


def test_provider_preference_skips_docker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
    monkeypatch.setenv("RUMI_SANDBOX_PROVIDER_PREFERENCE", "provider")
    fake_provider = FakeSandboxProvider()
    executor = ProviderAwareSecureExecutor(provider_sandbox_manager=ProviderSandboxManager([fake_provider]))
    monkeypatch.setattr(executor, "is_docker_available", lambda: True)

    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("def run(ctx): return {'ok': True}\n", encoding="utf-8")

    result = executor.execute_component_phase(
        pack_id="pack",
        component_id="component",
        phase="run",
        file_path=entrypoint,
        context={"payload": {"safe": True}},
        timeout=30,
    )

    assert result.success
    assert result.execution_mode == "sandbox:fake"
    assert len(fake_provider.requests) == 1


def test_execute_lib_uses_provider_without_docker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
    fake_provider = FakeSandboxProvider()
    executor = ProviderAwareSecureExecutor(provider_sandbox_manager=ProviderSandboxManager([fake_provider]))
    monkeypatch.setattr(executor, "is_docker_available", lambda: False)
    monkeypatch.setattr(executor, "_ensure_pack_data_dir", lambda pack_id: (True, tmp_path / "data"))
    (tmp_path / "data").mkdir()

    lib_file = tmp_path / "install.py"
    lib_file.write_text("def run(ctx): return {'installed': True}\n", encoding="utf-8")

    result = executor.execute_lib(
        pack_id="pack",
        lib_type="install",
        lib_file=lib_file,
        context={"payload": {"safe": True}},
        timeout=30,
    )

    assert result.success
    assert result.pack_id == "pack"
    assert result.lib_type == "install"
    assert fake_provider.requests[0].component_id == "lib:install"
    assert fake_provider.requests[0].metadata["kind"] == "lib"


def test_di_secure_executor_is_provider_aware() -> None:
    reset_container()
    try:
        executor = get_container().get("secure_executor")
        assert isinstance(executor, ProviderAwareSecureExecutor)
        assert get_container().has("provider_sandbox_manager")
    finally:
        reset_container()
