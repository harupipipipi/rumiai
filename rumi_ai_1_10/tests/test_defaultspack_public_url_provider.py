from __future__ import annotations

import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.webhook.url_providers.cloudflare_quick_tunnel import CloudflareQuickTunnelProvider  # noqa: E402
from domain.webhook.url_providers.static import StaticWebhookUrlProvider  # noqa: E402
from blocks.webhooks import public_url  # noqa: E402


def test_static_url_provider_builds_route_url():
    result = StaticWebhookUrlProvider().create_url(local_url="http://127.0.0.1:8787", route_path="/api/webhooks/inbound/test")
    assert result["public_url"] == "http://127.0.0.1:8787/api/webhooks/inbound/test"


def test_cloudflare_quick_tunnel_graceful_status():
    result = CloudflareQuickTunnelProvider().status("missing")
    assert result["ok"] is False
    assert "error" in result


def test_public_url_block_returns_static_url_with_runtime_default(monkeypatch):
    monkeypatch.setenv("DEFAULTS_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("DEFAULTS_HTTP_PORT", "8766")

    response = public_url.run(
        {
            "_method": "POST",
            "provider_id": "static",
            "route_path": "/api/integrations/line/webhook",
        },
        {},
    )

    assert response["status"] == "ok"
    assert response["data"]["public_url"] == "http://127.0.0.1:8766/api/integrations/line/webhook"


def test_public_url_block_reports_cloudflare_missing_without_error_envelope(monkeypatch):
    monkeypatch.setattr("domain.webhook.url_providers.cloudflare_quick_tunnel.shutil.which", lambda _: None)

    response = public_url.run(
        {
            "_method": "POST",
            "provider_id": "cloudflare_quick_tunnel",
            "local_url": "http://127.0.0.1:8766",
            "route_path": "/api/integrations/line/webhook",
        },
        {},
    )

    assert response["status"] == "ok"
    assert response["data"]["ok"] is False
    assert "cloudflared" in response["data"]["error"]


def test_cloudflare_quick_tunnel_requires_reachable_health(monkeypatch):
    import domain.webhook.url_providers.cloudflare_quick_tunnel as cloudflare_provider

    class FakeProcess:
        stdout = io.StringIO("https://ready-soon.trycloudflare.com\n")
        stderr = io.StringIO("")
        pid = 12345

        def __init__(self) -> None:
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.terminated = True

    fake_process = FakeProcess()
    monkeypatch.setattr(cloudflare_provider.shutil, "which", lambda _: "/usr/local/bin/cloudflared")
    monkeypatch.setattr(cloudflare_provider.subprocess, "Popen", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr(
        cloudflare_provider,
        "_wait_until_public_health_ready",
        lambda base_url, timeout_seconds=12: {"ok": False, "health_url": base_url + "/api/health", "error": "HTTP 530"},
    )

    result = CloudflareQuickTunnelProvider().create_url(
        local_url="http://127.0.0.1:8766",
        route_path="/api/integrations/line/webhook",
        context={"timeout_seconds": 1, "health_timeout_seconds": 1},
    )

    assert result["ok"] is False
    assert "not reachable" in result["error"]
    assert "public_url" not in result
    assert result["candidate_public_url"] == "https://ready-soon.trycloudflare.com/api/integrations/line/webhook"
    assert fake_process.terminated is True
