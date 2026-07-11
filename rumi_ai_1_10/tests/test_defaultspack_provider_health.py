from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _provider(report: dict, provider_id: str) -> dict:
    return next(item for item in report["providers"] if item["provider_id"] == provider_id)


def test_provider_catalog_reports_env_source_for_opencode_zen(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")

    from domain.ai_client.providers import get_provider_catalog_map

    catalog = get_provider_catalog_map()

    assert catalog["opencode-zen"]["availability"]["configured"] is True
    assert catalog["opencode-zen"]["availability"]["configuration_source"] == "OPENCODE_ZEN_API_KEY"


def test_provider_health_reports_env_backed_opencode_zen_without_secret_value(monkeypatch, tmp_path):
    secret_value = "test-opencode-zen-key"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", secret_value)

    from domain.ai_client.provider_health import provider_health_report

    report = provider_health_report(
        pack_root=DEFAULTSPACK_ROOT,
        provider_ids=["opencode-zen"],
    )
    provider = _provider(report, "opencode-zen")

    assert report["contract_version"] == "provider-health.v1"
    assert provider["status"] == "configured"
    assert provider["health_code"] == "ok"
    assert provider["runtime"]["configuration_source"] == "OPENCODE_ZEN_API_KEY"
    assert provider["credential"]["configured"] is True
    assert provider["credential"]["source"] == "env"
    assert provider["credential"]["source_detail"] == "OPENCODE_ZEN_API_KEY"
    assert provider["credential"]["masked"] is True
    assert provider["models"]["default_model_for"]["cheap"] == "mimo-v2.5-free"
    assert "provider_key_source_mismatch" not in {
        item["code"] for item in provider["diagnostics"]
    }
    assert secret_value not in json.dumps(report)


def test_provider_health_marks_missing_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)

    from domain.ai_client.provider_health import provider_health_report

    report = provider_health_report(
        pack_root=DEFAULTSPACK_ROOT,
        provider_ids=["opencode-zen"],
    )
    provider = _provider(report, "opencode-zen")

    assert provider["status"] == "missing_credentials"
    assert provider["health_code"] == "auth_missing"
    assert provider["credential"]["source"] == "none"
    assert "auth_missing" in {item["code"] for item in provider["diagnostics"]}


def test_provider_health_route_is_registered_and_block_returns_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")

    from blocks.ui.provider_health import run
    from blocks.ui.setup import run as setup_ui_routes
    from transport.registry import build_fallback_http_routes

    class FakeInterfaceRegistry:
        def __init__(self):
            self.routes = []

        def register(self, key, value, meta=None):
            del meta
            if key == "io.http.route":
                self.routes.append(value)

    class FakeServer:
        def __getattr__(self, name):
            if str(name).startswith("_handle_authority_"):
                return lambda *_args, **_kwargs: {"status": "ok"}
            raise AttributeError(name)

        def _invoke_fallback_block(self, module_name, request_data, path_params, inject=None):
            return {
                "status": "ok",
                "module_name": module_name,
                "request_data": request_data,
                "path_params": path_params,
                "inject": inject,
            }

        def _handle_health(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _handle_context_info(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _handle_desktop_system_info(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _handle_chat_redirect(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _handle_static(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _handle_static_file(self, *_args, **_kwargs):
            return {"status": "ok"}

    registry = FakeInterfaceRegistry()
    setup_ui_routes({"interface_registry": registry})
    registered_patterns = {route["pattern"] for route in registry.routes}
    fallback_patterns = {
        compiled.pattern for _, compiled, _, _, _ in build_fallback_http_routes(FakeServer())
    }
    normalized_fallback_patterns = {pattern.replace("\\-", "-") for pattern in fallback_patterns}
    response = run({"provider_id": "opencode-zen"}, {})

    assert "/api/ui/provider-health" in registered_patterns
    assert any("api/ui/provider-health" in pattern for pattern in normalized_fallback_patterns)
    assert response["status"] == "ok"
    assert response["data"]["contract_version"] == "provider-health.v1"
    assert _provider(response["data"], "opencode-zen")["credential"]["source"] == "env"
