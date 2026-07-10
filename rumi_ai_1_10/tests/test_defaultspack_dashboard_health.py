from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_dashboard_health_redacts_provider_and_gateway_secrets(monkeypatch):
    from blocks.ai import dashboard_health

    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("RUMI_TUNNEL_URL", "https://secret-tunnel.example")
    monkeypatch.setenv("RUMI_WEBHOOK_URL", "https://secret-webhook.example")
    monkeypatch.setattr(
        dashboard_health,
        "_authority_requests",
        lambda: [
            {
                "request_id": "req_1",
                "status": "pending",
                "permission_id": "tool.execute",
                "risk_level": "high",
                "resource": {"path": "/tmp/private", "replayed": True},
                "display_summary": "Run /tmp/private with sk-should-not-leak",
                "reason": "Needs approval for /tmp/private using sk-should-not-leak",
                "created_at": "2026-07-05T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        "domain.ai_client.api_key_store.provider_key_status",
        lambda: [
            {
                "provider_id": "openai",
                "key": "OPENAI_API_KEY",
                "configured": True,
                "apis": [{"quota_label": "free-tier", "key": "RUMIAPI_OPENAI_DEFAULT"}],
                "oauth": {},
            }
        ],
    )
    monkeypatch.setattr(
        "ecosystem.defaultspack.backend.ai_client.provider_catalog.list_provider_catalog",
        lambda: [{"provider_id": "openai", "display_name": "OpenAI", "kind": "cloud"}],
    )

    class Client:
        def list_providers(self):
            return [{"provider_id": "openai"}]

    monkeypatch.setattr("ecosystem.defaultspack.domain.ai_client.client.AIClient", Client)

    payload = dashboard_health.build_dashboard_health()
    serialized = str(payload)

    assert payload["provider"]["providers"][0]["key_source"] == "named_api_key"
    assert payload["approval"]["pending"] == 1
    assert payload["approval"]["risky"] == 1
    assert payload["approval"]["replayed"] == 1
    assert payload["approval"]["recent"][0]["summary"] == "tool.execute: pending / high"
    assert payload["gateway"]["tunnel_url"] == "configured"
    assert "sk-should-not-leak" not in serialized
    assert "secret-tunnel" not in serialized
    assert "secret-webhook" not in serialized
    assert "/tmp/private" not in serialized


def test_provider_failure_classification_uses_stable_codes():
    from blocks.ai.dashboard_health import (
        PROVIDER_FAILURE_AUTH_MISSING,
        PROVIDER_FAILURE_RUNTIME_UNREGISTERED,
        classify_provider_failure,
    )

    assert classify_provider_failure(
        {"auth_mode": "api_key", "configured": False, "registered": False}
    )["code"] == PROVIDER_FAILURE_AUTH_MISSING
    assert classify_provider_failure(
        {"auth_mode": "api_key", "configured": True, "registered": False}
    )["code"] == PROVIDER_FAILURE_RUNTIME_UNREGISTERED
