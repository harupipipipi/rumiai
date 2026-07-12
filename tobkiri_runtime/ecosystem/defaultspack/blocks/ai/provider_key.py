"""Approved compatibility adapter for provider connections and credentials."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from blocks._common import error, ok
from blocks.coding._approval import (
    approval_invalid_response,
    approval_required,
    is_server_approved,
)
from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import invoke_global_contract

_CREDENTIAL_MANAGE = "rumi.action.credential.manage.v1"
_CREDENTIAL_STATUS = "rumi.resource.credential.status.v1"
_PROVIDER_MANAGE = "rumi.action.ai.provider.registry.manage.v1"
_PROVIDER_RESOURCE = "rumi.resource.ai.provider.registry.v1"


def run(input_data, context):
    """Preserve the finite legacy route without owning either resource."""
    data = dict(input_data or {})
    method = str(data.get("_method") or "GET").upper()
    if method == "GET":
        return ok(_status())
    if method != "POST":
        return error("unsupported method", "METHOD_NOT_ALLOWED")
    action = str(data.get("action") or "upsert").strip().lower()
    provider_id = str(data.get("provider_id") or "").strip()
    operation = f"ai.provider_key.{action}"
    approval_data = _approval_data(data)
    invalid = approval_invalid_response(operation, approval_data, error)
    if invalid is not None:
        return invalid
    approved = is_server_approved(
        context,
        operation=operation,
        input_data=approval_data,
    )
    if not approved:
        return ok(
            approval_required(
                operation,
                "high",
                args=approval_data,
                provider_id=provider_id,
            )
        )
    if not provider_id:
        return error("provider_id is required", "MISSING_PARAM")
    try:
        if action in {"delete", "delete_provider"}:
            return ok(_delete(provider_id))
        if action == "rename":
            return ok(_rename(provider_id, data))
        if action == "register_provider":
            return ok(_save_connection(provider_id, data, credential_handle=None))
        if action != "upsert":
            return error("unsupported action", "INVALID_ACTION")
        return ok(_upsert(provider_id, data))
    except (KeyError, RuntimeError, ValueError) as exc:
        return error(type(exc).__name__, "PROVIDER_CONNECTION_FAILED")


def _status() -> dict[str, Any]:
    credentials = _invoke(_CREDENTIAL_STATUS, "list", {})
    providers = _invoke(_PROVIDER_RESOURCE, "list", {})
    credential_items = (
        credentials.get("credentials") if isinstance(credentials, Mapping) else []
    )
    provider_items = (
        providers.get("providers") if isinstance(providers, Mapping) else []
    )
    provider_items = provider_items if isinstance(provider_items, list) else []
    return {
        "providers": [
            {
                "provider_id": str(
                    item.get("provider_instance_id") or ""
                ).removeprefix("provider."),
                "configured": bool(item.get("enabled", True)),
                "credential_handle": item.get("credential_handle"),
                "base_url": item.get("endpoint"),
                "kind": item.get("adapter_id"),
            }
            for item in provider_items
            if isinstance(item, Mapping)
        ],
        "credentials": (
            [dict(item) for item in credential_items if isinstance(item, Mapping)]
            if isinstance(credential_items, list) else []
        ),
        "custom_providers": [],
    }


def _upsert(provider_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    secret = str(data.get("value") or "")
    if not secret:
        raise ValueError("provider credential value is required")
    provider_instance_id = f"provider.{provider_id}"
    created = _invoke(
        _CREDENTIAL_MANAGE,
        "create",
        {
            "secret_material": {"api_key": secret},
            "consumer_pack_id": "rumi_provider_adapters_pack",
            "provider_instance_id": provider_instance_id,
            "scopes": ["ai.generate", "ai.stream"],
            "label": str(data.get("name") or provider_id),
        },
    )
    handle = str(created.get("handle") or "")
    try:
        result = _save_connection(provider_id, data, credential_handle=handle)
    except Exception:
        _invoke(_CREDENTIAL_MANAGE, "revoke", {"handle": handle})
        raise
    return {**result, "configured": True}


def _save_connection(
    provider_id: str,
    data: Mapping[str, Any],
    *,
    credential_handle: str | None,
) -> dict[str, Any]:
    snapshot = _invoke(_PROVIDER_RESOURCE, "list", {})
    revision = int(snapshot.get("revision") or 0)
    endpoint = str(data.get("base_url") or data.get("endpoint") or "").strip()
    if not endpoint:
        raise ValueError("provider endpoint is required")
    adapter_id = str(data.get("kind") or "openai-compatible").strip()
    result = _invoke(
        _PROVIDER_MANAGE,
        "save",
        {
            "expected_revision": revision,
            "record": {
                "provider_instance_id": f"provider.{provider_id}",
                "adapter_id": adapter_id,
                "display_name": str(
                    data.get("label") or data.get("name") or provider_id
                ),
                "credential_handle": credential_handle,
                "endpoint": endpoint,
                "enabled": True,
                "metadata": {"legacy_api_id": str(data.get("api_id") or "default")},
            },
        },
    )
    return {
        "success": True,
        "provider_id": provider_id,
        "configured": True,
        "provider": result.get("provider"),
    }


def _delete(provider_id: str) -> dict[str, Any]:
    snapshot = _invoke(_PROVIDER_RESOURCE, "list", {})
    providers = snapshot.get("providers") if isinstance(snapshot, Mapping) else []
    providers = providers if isinstance(providers, list) else []
    expected_id = f"provider.{provider_id}"
    record = next(
        (
            dict(item)
            for item in providers
            if isinstance(item, Mapping)
            and item.get("provider_instance_id") == expected_id
        ),
        None,
    )
    if record is None:
        raise KeyError("provider connection is unknown")
    _invoke(
        _PROVIDER_MANAGE,
        "delete",
        {
            "provider_instance_id": expected_id,
            "expected_revision": int(snapshot.get("revision") or 0),
        },
    )
    handle = record.get("credential_handle")
    if handle:
        _invoke(_CREDENTIAL_MANAGE, "revoke", {"handle": handle})
    return {"success": True, "provider_id": provider_id, "configured": False}


def _rename(provider_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _invoke(_PROVIDER_RESOURCE, "list", {})
    providers = snapshot.get("providers") if isinstance(snapshot, Mapping) else []
    providers = providers if isinstance(providers, list) else []
    expected_id = f"provider.{provider_id}"
    record = next(
        (
            dict(item)
            for item in providers
            if isinstance(item, Mapping)
            and item.get("provider_instance_id") == expected_id
        ),
        None,
    )
    if record is None:
        raise KeyError("provider connection is unknown")
    record["display_name"] = str(data.get("name") or provider_id)
    result = _invoke(
        _PROVIDER_MANAGE,
        "save",
        {"record": record, "expected_revision": int(snapshot.get("revision") or 0)},
    )
    return {
        "success": True,
        "provider_id": provider_id,
        "provider": result.get("provider"),
    }


def _approval_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Bind approval to a secret digest without persisting secret material."""
    result = dict(data)
    secret = str(result.pop("value", ""))
    if secret:
        result["value_sha256"] = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return result


def _invoke(contract_id: str, operation: str, payload: Mapping[str, Any]) -> Any:
    registry = get_container().get_or_none("interface_registry")
    if registry is None:
        raise RuntimeError("interface registry is unavailable")
    return invoke_global_contract(registry, contract_id, operation, dict(payload))
