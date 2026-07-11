from __future__ import annotations

import importlib.util
import json
import sys
import types
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
BLOCK_PATH = DEFAULTSPACK_ROOT / "blocks" / "ui" / "client_events.py"
RAW_TOKEN = "sk-diagnostic-supersecretvalue"
RAW_EMAIL = "private.user@example.test"
RAW_PATH = "/Users/alice/workspace/secret.py"
RAW_URL = f"https://internal.example.test/private?access_token={RAW_TOKEN}#fragment"


def _load_block(monkeypatch):
    records: list[dict] = []

    common = types.ModuleType("_common")
    common.error = lambda message, code: {"status": "error", "error": {"message": message, "code": code}}
    common.ok = lambda data: {"status": "ok", "data": data}

    domain = types.ModuleType("domain")
    domain.__path__ = [str(DEFAULTSPACK_ROOT / "domain")]
    safety = types.ModuleType("domain.safety")
    safety.__path__ = [str(DEFAULTSPACK_ROOT / "domain" / "safety")]
    audit = types.ModuleType("domain.safety.audit")

    def append_record(record):
        records.append(record)
        return {"id": f"diag_{len(records)}"}

    audit.append_record = append_record
    monkeypatch.setitem(sys.modules, "_common", common)
    monkeypatch.setitem(sys.modules, "domain", domain)
    monkeypatch.setitem(sys.modules, "domain.safety", safety)
    monkeypatch.setitem(sys.modules, "domain.safety.audit", audit)

    module_name = f"test_client_events_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, BLOCK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, records


def _payload(**updates):
    payload = {
        "_method": "POST",
        "schema_version": "rumi.client_diagnostic.v2",
        "event_id": "event-client-value",
        "session_id": "session-client-value",
        "source": "window.error",
        "category": "window_error",
        "level": "error",
        "message": "Unhandled window error",
        "fingerprint": "diag-client-value",
        "context_id": "ctx-client-value",
        "privacy_mode": "standard",
        "detail": {
            "error_name": "TypeError",
            "error_code": "E_RENDER",
            "route": "/src/App.tsx",
            "line": 42,
            "column": 7,
            "stack": "at App (/src/App.tsx:42:7)",
        },
    }
    payload.update(updates)
    return payload


def _serialized(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def test_server_redacts_again_and_stores_only_allowlisted_fields(monkeypatch):
    block, records = _load_block(monkeypatch)
    payload = _payload(
        message=f"Provider failed at {RAW_URL} for {RAW_EMAIL} Authorization: Bearer {RAW_TOKEN}",
        context_id=f"conversation-private {RAW_EMAIL}",
        detail={
            "error_name": "ProviderError",
            "error_code": "HTTP_401",
            "route": RAW_URL,
            "line": 12,
            "column": 4,
            "stack": "\n".join(
                [
                    f"Error: private prompt {RAW_TOKEN}",
                    "at App (https://rumi.test/src/App.tsx?token=secret:12:4)",
                    "at dependency (https://cdn.test/node_modules/pkg/index.js:1:1)",
                    f"at local ({RAW_PATH}:2:3)",
                ]
            ),
            "component_stack": "at App\nat SecretPromptComponent",
            "prompt": "private prompt text",
            "messages": [{"role": "user", "content": "private prompt text"}],
            "tool_args": {"token": RAW_TOKEN},
            "tool_result": "tool output secret",
            "provider_payload": {"email": RAW_EMAIL},
            "authorization": f"Bearer {RAW_TOKEN}",
        },
    )

    result = block.run(payload, {})

    assert result["status"] == "ok"
    assert result["data"]["recorded"] is True
    assert len(records) == 1
    record = records[0]
    assert record["schema_version"] == "rumi.client_diagnostic.v2"
    assert record["privacy_mode"] == "standard"
    assert record["retention_class"] == "short"
    assert record["contains_user_content"] is False
    assert record["event_id"].startswith("event_")
    assert record["session_id"].startswith("session_")
    assert record["fingerprint"].startswith("diag_")
    assert record["context_id"].startswith("ctx_")
    assert set(record["details"]) <= {
        "error_name",
        "error_code",
        "route",
        "line",
        "column",
        "stack",
        "component_stack",
        "reason_type",
        "http_status",
        "frame_count",
    }
    serialized = _serialized(record)
    for sensitive in (RAW_TOKEN, RAW_EMAIL, RAW_PATH, RAW_URL, "private prompt text", "tool output secret"):
        assert sensitive not in serialized
    assert "node_modules" not in serialized
    assert "conversation_id" not in record


def test_server_rejects_unknown_fields_old_schema_and_non_remote_privacy_modes(monkeypatch):
    block, records = _load_block(monkeypatch)

    unknown = block.run(_payload(prompt="private prompt text"), {})
    assert unknown["status"] == "error"
    assert unknown["error"]["code"] == "INVALID_INPUT"

    old_schema = block.run(_payload(schema_version="rumi.client_diagnostic.v1"), {})
    assert old_schema["status"] == "error"
    assert old_schema["error"]["code"] == "INVALID_SCHEMA"

    for privacy_mode in ("private", "local_only", "disabled"):
        blocked = block.run(_payload(privacy_mode=privacy_mode), {})
        assert blocked["status"] == "error"
        assert blocked["error"]["code"] == "PRIVACY_MODE_BLOCKED"

    assert records == []


def test_server_rejects_oversized_and_circular_payloads_without_persisting(monkeypatch):
    block, records = _load_block(monkeypatch)

    oversized = block.run(_payload(message="x" * (block.MAX_PAYLOAD_BYTES + 1)), {})
    assert oversized["status"] == "error"
    assert oversized["error"]["code"] == "PAYLOAD_TOO_LARGE"

    circular = _payload()
    circular["detail"] = circular
    cycle_result = block.run(circular, {})
    assert cycle_result["status"] == "error"
    assert cycle_result["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert records == []


def test_server_enforces_process_local_rate_limit(monkeypatch):
    block, records = _load_block(monkeypatch)

    for index in range(block.RATE_LIMIT):
        result = block.run(_payload(event_id=f"event-{index}", fingerprint=f"diag-{index}"), {})
        assert result["status"] == "ok"

    limited = block.run(_payload(event_id="event-over-limit", fingerprint="diag-over-limit"), {})
    assert limited["status"] == "error"
    assert limited["error"]["code"] == "RATE_LIMITED"
    assert len(records) == block.RATE_LIMIT
