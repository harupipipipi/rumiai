from __future__ import annotations

import os
import secrets
import time
from typing import Any

from domain.chat.store import ChatStore
from domain.external.token_store import delete_external_token, read_external_token, set_external_token
from domain.webhook.endpoint_store import WebhookEndpointStore
from domain.webhook.inbound import handle_inbound_webhook


def create_local_hook(args: dict[str, Any]) -> dict[str, Any]:
    conversation_id = str(args.get("conversation_id") or "").strip()
    if not conversation_id:
        return _error("conversation_id is required", "INVALID_INPUT")
    clone_strategy = str(args.get("clone_strategy") or "none").strip() or "none"
    if clone_strategy not in {"none", "clone_now", "clone_on_call"}:
        return _error("clone_strategy must be none, clone_now, or clone_on_call", "INVALID_INPUT")

    target_conversation_id = conversation_id
    cloned_conversation_id = ""
    if clone_strategy == "clone_now":
        clone = ChatStore().clone_conversation(
            conversation_id,
            system_prompt_override=args.get("system_prompt_override"),
            model_override=args.get("model_override"),
            metadata={"local_hook": True, "clone_strategy": clone_strategy},
            title=args.get("title") or "Local Hook Conversation",
            conversation_kind="local_hook_clone",
        )
        if clone is None:
            return _error("source conversation not found", "NOT_FOUND")
        target_conversation_id = str(clone.get("id") or "")
        cloned_conversation_id = target_conversation_id

    ttl_seconds = _ttl(args.get("ttl_seconds"))
    endpoint_id = str(args.get("endpoint_id") or args.get("id") or "").strip()
    if not endpoint_id:
        endpoint_id = f"local-hook-{int(time.time() * 1000)}"
    secret = str(args.get("shared_secret") or args.get("secret") or secrets.token_urlsafe(24))
    default_delivery = dict(args.get("default_delivery") if isinstance(args.get("default_delivery"), dict) else {})
    default_delivery.setdefault("action_id", "chat.message")
    payload = {
        "id": endpoint_id,
        "kind": "local_hook",
        "input_profile_id": "generic.webhook.default",
        "enabled": True,
        "target": {"conversation_id": target_conversation_id, "direct": True},
        "default_delivery": default_delivery,
        "allowed_delivery_actions": [str(default_delivery.get("action_id") or "chat.message")],
        "ttl_seconds": ttl_seconds,
        "expires_at": int(time.time() * 1000) + ttl_seconds * 1000 if ttl_seconds else None,
        "security": {"mode": "shared_secret", "header": "x-rumi-webhook-token"},
        "metadata": {
            "local_hook": True,
            "source_conversation_id": conversation_id,
            "clone_strategy": clone_strategy,
            "system_prompt_override": str(args.get("system_prompt_override") or ""),
            "model_override": str(args.get("model_override") or ""),
            "cloned_conversation_id": cloned_conversation_id,
        },
    }
    created = WebhookEndpointStore().upsert(payload)
    set_external_token("local_hook", secret, token_id=endpoint_id, kind="webhook_shared_secret")
    endpoint = created.get("endpoint") if isinstance(created.get("endpoint"), dict) else {}
    localhost_url = _localhost_url(endpoint_id)
    return _ok(
        {
            "endpoint": endpoint,
            "endpoint_id": endpoint_id,
            "localhost_url": localhost_url,
            "secret": secret,
            "header": "x-rumi-webhook-token",
            "conversation_id": target_conversation_id,
            "source_conversation_id": conversation_id,
            "cloned_conversation_id": cloned_conversation_id,
            "clone_strategy": clone_strategy,
            "snippets": _snippets(localhost_url, secret),
        }
    )


def list_local_hooks(args: dict[str, Any] | None = None) -> dict[str, Any]:
    del args
    hooks = []
    for endpoint in WebhookEndpointStore().list_endpoints():
        metadata = endpoint.get("metadata") if isinstance(endpoint.get("metadata"), dict) else {}
        if metadata.get("local_hook") is True or str(endpoint.get("kind") or "") == "local_hook":
            item = dict(endpoint)
            item["localhost_url"] = _localhost_url(str(endpoint.get("id") or ""))
            hooks.append(item)
    return _ok({"hooks": hooks})


def delete_local_hook(args: dict[str, Any]) -> dict[str, Any]:
    endpoint_id = str(args.get("endpoint_id") or args.get("id") or "").strip()
    if not endpoint_id:
        return _error("endpoint_id is required", "INVALID_INPUT")
    deleted = WebhookEndpointStore().delete(endpoint_id)
    delete_external_token("local_hook", endpoint_id)
    delete_external_token("generic", endpoint_id)
    return _ok(deleted)


def test_local_hook(args: dict[str, Any]) -> dict[str, Any]:
    endpoint_id = str(args.get("endpoint_id") or args.get("id") or "").strip()
    if not endpoint_id:
        return _error("endpoint_id is required", "INVALID_INPUT")
    token = str(args.get("secret") or args.get("shared_secret") or "").strip()
    if not token:
        token = read_external_token("local_hook", token_id=endpoint_id, kind="webhook_shared_secret")
    text = str(args.get("text") or args.get("message") or "local hook test").strip()
    payload = {
        "text": text,
        "token": token,
        "provider": "local",
        "scope_type": "local_hook",
        "delivery": args.get("delivery") if isinstance(args.get("delivery"), dict) else {},
    }
    result = handle_inbound_webhook(endpoint_id, payload, {"source": "local_hook_test"})
    return _ok({"result": result})


def _ttl(value: Any) -> int:
    try:
        parsed = int(value) if value not in (None, "") else 3600
    except (TypeError, ValueError):
        parsed = 3600
    return max(parsed, 1)


def _localhost_url(endpoint_id: str) -> str:
    port = int(os.environ.get("DEFAULTS_HTTP_PORT", "8766"))
    return f"http://localhost:{port}/api/webhooks/inbound/{endpoint_id}"


def _snippets(url: str, secret: str) -> dict[str, str]:
    return {
        "curl": (
            "curl -X POST "
            f"-H 'content-type: application/json' -H 'x-rumi-webhook-token: {secret}' "
            f"-d '{{\"text\":\"hello from local code\"}}' {url}"
        ),
        "fetch": (
            "await fetch("
            f"{url!r}, "
            "{method:'POST',headers:{'content-type':'application/json','x-rumi-webhook-token':"
            f"{secret!r}"
            "},body:JSON.stringify({text:'hello from local code'})})"
        ),
    }


def _ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data}


def _error(message: str, code: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}
