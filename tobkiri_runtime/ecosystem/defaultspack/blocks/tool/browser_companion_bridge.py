from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from ecosystem.rumi_default_tools_pack.domain.tool.browser_companion import BrowserCompanionController
from ecosystem.rumi_default_tools_pack.domain.tool.browser_companion_bridge import (
    BrowserCompanionBridgeStore,
    bearer_token_from_headers,
)


def _authorized_store(input_data, *, scope):
    store = BrowserCompanionBridgeStore()
    headers = input_data.get("_headers") if isinstance(input_data.get("_headers"), dict) else {}
    token = str(input_data.get("_browser_companion_bearer") or "") or bearer_token_from_headers(headers)
    client = input_data.get("client") if isinstance(input_data.get("client"), dict) else input_data
    client_id = str(input_data.get("client_id") or client.get("client_id") or "")
    installation_id = str(client.get("installation_id") or "")
    if not store.authorize_device(token, client_id=client_id, installation_id=installation_id, scope=scope):
        response = error("invalid, expired, revoked, or wrong-device browser credential", code="DEVICE_CREDENTIAL_UNAUTHORIZED")
        response["_http_status"] = 401
        return None, response
    return store, None


def run_session(input_data=None, context=None):
    del input_data
    controller = BrowserCompanionController(bridge_store=BrowserCompanionBridgeStore())
    return ok(controller.run("session", {}, context=context if isinstance(context, dict) else {}))


def run_poll(input_data, context=None):
    store, failure = _authorized_store(input_data if isinstance(input_data, dict) else {}, scope="bridge.poll")
    if failure is not None:
        return failure
    payload = dict(input_data.get("client") or input_data or {})
    client = store.upsert_client(payload)
    command = store.claim_next_command(str(client.get("client_id") or ""))
    return ok(
        {
            "accepted": True,
            "client_id": client.get("client_id"),
            "command": _public_command(command),
            "commands": [_public_command(command)] if isinstance(command, dict) else [],
        }
    )


def run_result(input_data, context=None):
    store, failure = _authorized_store(input_data if isinstance(input_data, dict) else {}, scope="bridge.result")
    if failure is not None:
        return failure
    payload = input_data if isinstance(input_data, dict) else {}
    client_payload = dict(payload.get("client") or {})
    client_id = str(payload.get("client_id") or client_payload.get("client_id") or "")
    if client_id:
        client_payload["client_id"] = client_id
    try:
        client = store.upsert_client(client_payload)
    except KeyError as exc:
        response = error(str(exc), code="UNKNOWN_COMMAND")
        response["_http_status"] = 404
        return response
    except ValueError as exc:
        response = error(str(exc), code="COMMAND_CLIENT_MISMATCH")
        response["_http_status"] = 409
        return response
    records = []
    try:
        raw_results = payload.get("results")
        if isinstance(raw_results, list):
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                command_id = str(item.get("command_id") or "")
                if not command_id:
                    continue
                record = store.complete_command(
                    str(client.get("client_id") or ""),
                    command_id,
                    _normalized_result(item),
                )
                records.append(record)
        else:
            command_id = str(payload.get("command_id") or "")
            if not command_id:
                response = error("client_id and command_id are required", code="INVALID_INPUT")
                response["_http_status"] = 400
                return response
            record = store.complete_command(
                str(client.get("client_id") or ""),
                command_id,
                _normalized_result(payload),
            )
            records.append(record)
    except KeyError as exc:
        response = error(str(exc), code="UNKNOWN_COMMAND")
        response["_http_status"] = 404
        return response
    except ValueError as exc:
        response = error(str(exc), code="COMMAND_CLIENT_MISMATCH")
        response["_http_status"] = 409
        return response
    return ok(
        {
            "accepted": True,
            "command_id": records[0].get("command_id") if records else None,
            "command_ids": [record.get("command_id") for record in records],
        }
    )


def run_exchange(input_data=None, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    store = BrowserCompanionBridgeStore()
    try:
        credential = store.exchange_pairing(str(payload.get("pairing_code") or ""), client_id=str(payload.get("client_id") or ""), installation_id=str(payload.get("installation_id") or ""))
    except (PermissionError, ValueError) as exc:
        response = error(str(exc), code="PAIRING_EXCHANGE_DENIED")
        response["_http_status"] = 401
        return response
    return ok({"credential": credential})


def run_refresh(input_data=None, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    try:
        credential = BrowserCompanionBridgeStore().rotate_access(str(payload.get("refresh_token") or ""), client_id=str(payload.get("client_id") or ""), installation_id=str(payload.get("installation_id") or ""))
    except PermissionError as exc:
        response = error(str(exc), code="DEVICE_REFRESH_DENIED")
        response["_http_status"] = 401
        return response
    return ok({"credential": credential})


def run_revoke(input_data=None, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    revoked = BrowserCompanionBridgeStore().revoke_device(str(payload.get("credential_id") or ""), refresh_token=str(payload.get("refresh_token") or ""), client_id=str(payload.get("client_id") or ""), installation_id=str(payload.get("installation_id") or ""))
    if not revoked:
        response = error("device credential revocation denied", code="DEVICE_REVOKE_DENIED")
        response["_http_status"] = 401
        return response
    return ok({"revoked": True})


def _public_command(record):
    if not isinstance(record, dict):
        return None
    return {
        "command_id": record.get("command_id"),
        "action": (record.get("request") or {}).get("action"),
        "payload": (record.get("request") or {}).get("payload") or {},
        "created_at": record.get("created_at"),
    }


def _normalized_result(payload):
    if not isinstance(payload, dict):
        return {}
    raw_result = payload.get("result")
    result = dict(raw_result) if isinstance(raw_result, dict) else {}
    if not result:
        result = {
            key: value
            for key, value in payload.items()
            if key not in {"command_id", "client_id", "type", "ok", "started_at", "finished_at", "error", "result"}
        }
    if payload.get("ok") is False:
        result["is_error"] = True
        if not result.get("reason"):
            result["reason"] = payload.get("error") or "Browser companion command failed."
    elif payload.get("ok") is True and "is_error" not in result:
        result["is_error"] = False
    return result
