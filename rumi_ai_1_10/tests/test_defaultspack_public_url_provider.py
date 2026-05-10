from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.webhook.url_providers.cloudflare_quick_tunnel import CloudflareQuickTunnelProvider  # noqa: E402
from domain.webhook.url_providers.static import StaticWebhookUrlProvider  # noqa: E402


def test_static_url_provider_builds_route_url():
    result = StaticWebhookUrlProvider().create_url(local_url="http://127.0.0.1:8787", route_path="/api/webhooks/inbound/test")
    assert result["public_url"] == "http://127.0.0.1:8787/api/webhooks/inbound/test"


def test_cloudflare_quick_tunnel_graceful_status():
    result = CloudflareQuickTunnelProvider().status("missing")
    assert result["ok"] is False
    assert "error" in result
