from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_cloudflare_sdk_adapter_reports_missing_sdk(monkeypatch):
    from core_runtime.cloudflare import sdk_client

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    status = sdk_client.cloudflare_sdk_status()
    adapter_status = sdk_client.CloudflareSDKAdapter(api_token="secret", account_id="acct").status()

    assert status["available"] is False
    assert status["status"] == "sdk_missing"
    assert adapter_status["status"] == "sdk_missing"
    assert adapter_status["token_configured"] is True
    assert adapter_status["account_configured"] is True


def test_cloudflare_oauth_status_includes_sdk_missing(monkeypatch):
    from core_runtime.cloudflare import sdk_client
    from domain.ai_client.oauth_store import provider_oauth_status

    monkeypatch.setattr(sdk_client.importlib.util, "find_spec", lambda _name: None)

    status = provider_oauth_status("cloudflare")

    assert status["cloudflare_sdk"]["status"] == "sdk_missing"
    assert status["provisioning"]["sdk_status"] == "sdk_missing"
