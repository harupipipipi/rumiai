from __future__ import annotations


def test_kernel_api_init_port_prefers_runtime_env(monkeypatch):
    from core_runtime.kernel_handlers_system import _resolve_api_port

    monkeypatch.setenv("RUMI_PORT", "8768")

    assert _resolve_api_port({"port": 8765}) == 8768


def test_kernel_api_init_port_falls_back_to_flow_arg(monkeypatch):
    from core_runtime.kernel_handlers_system import _resolve_api_port

    monkeypatch.delenv("RUMI_PORT", raising=False)

    assert _resolve_api_port({"port": 8765}) == 8765
