from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.token_store import set_external_token  # noqa: E402
from domain.webhook.endpoint import WebhookEndpoint  # noqa: E402
from domain.webhook.endpoint_store import WebhookEndpointStore  # noqa: E402
from domain.webhook.inbound import verify_endpoint_security  # noqa: E402


def test_endpoint_store_crud_and_shared_secret_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        endpoint_path = Path(tmpdir) / "endpoints.json"
        secrets_dir = Path(tmpdir) / "secrets"
        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
            store = WebhookEndpointStore(endpoint_path)
            result = store.upsert(
                {
                    "id": "test-webhook",
                    "kind": "generic",
                    "input_profile_id": "generic.webhook.default",
                    "security": {"mode": "shared_secret", "header": "x-rumi-webhook-token"},
                    "enabled": True,
                }
            )
            set_external_token("generic", "secret", token_id="test-webhook", kind="webhook_shared_secret")

            endpoint = result["endpoint"]
            assert verify_endpoint_security(endpoint, {"_headers": {"x-rumi-webhook-token": "secret"}})["ok"] is True
            assert verify_endpoint_security(endpoint, {"_headers": {"x-rumi-webhook-token": "bad"}})["ok"] is False
            assert store.delete("test-webhook")["deleted"] is True


def test_endpoint_as_dict_redacts_inline_secret():
    endpoint = WebhookEndpoint(
        id="test",
        kind="generic",
        input_profile_id="generic.webhook.default",
        security={"mode": "shared_secret", "token": "secret-value"},
        metadata={"refresh_token": "also-secret"},
    )

    public_endpoint = endpoint.as_dict()
    assert public_endpoint["security"]["token"] == "***"
    assert public_endpoint["metadata"]["refresh_token"] == "***"
    assert endpoint.as_dict(redact=False)["security"]["token"] == "secret-value"
