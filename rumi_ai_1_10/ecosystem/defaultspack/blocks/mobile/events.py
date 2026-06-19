"""blocks.mobile.events — イベント・承認のポーリング取得.

モバイルがPC上のツール実行状況や承認要求を取得するためのエンドポイント。
SSEストリーミングの補完として、ポーリングベースでイベントを取得できる。

ルート:
  GET  /api/mobile/v1/events?after={cursor}    → イベント一覧
  GET  /api/mobile/v1/approvals                → 承認待ち一覧
  POST /api/mobile/v1/approvals/{id}/approve   → 承認
  POST /api/mobile/v1/approvals/{id}/deny      → 拒否
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok


def _merged(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        return {}
    merged: dict = {}
    for container_key in ("query_params", "params", "body", "path_params", "query"):
        value = input_data.get(container_key)
        if isinstance(value, dict):
            merged.update(value)
    for key, value in input_data.items():
        if key in {"query_params", "params", "body", "path_params", "query"}:
            continue
        merged[key] = value
    return merged


def list_events(input_data, context=None):
    args = _merged(input_data)
    cursor = str(args.get("after") or args.get("cursor") or "event-0")
    # Delegate to existing authority event stream
    try:
        from core_runtime.authority import get_authority_service
        service = get_authority_service()
        events = service.events(after=cursor, limit=50)
        return ok({"events": events, "cursor": f"event-{len(events)}"})
    except Exception:
        return ok({"events": [], "cursor": cursor})


def list_approvals(input_data, context=None):
    del input_data, context
    try:
        from core_runtime.authority import get_authority_service
        service = get_authority_service()
        requests = service.list_requests(status="pending")
        return ok({"approvals": requests})
    except Exception:
        return ok({"approvals": []})


def approve_approval(input_data, context=None):
    args = _merged(input_data)
    request_id = str(args.get("request_id") or args.get("id") or "").strip()
    if not request_id:
        return error("request_id is required", "INVALID_INPUT")
    scope = str(args.get("scope") or "once").strip()
    try:
        from core_runtime.authority import get_authority_service
        service = get_authority_service()
        result = service.approve_request(
            request_id,
            scope=scope,
            config=args.get("config") if isinstance(args.get("config"), dict) else None,
            expires_in_seconds=int(args.get("expires_in_seconds") or 300),
        )
        return ok({"result": result})
    except Exception as exc:
        return error(str(exc), "APPROVE_FAILED")


def deny_approval(input_data, context=None):
    args = _merged(input_data)
    request_id = str(args.get("request_id") or args.get("id") or "").strip()
    if not request_id:
        return error("request_id is required", "INVALID_INPUT")
    reason = str(args.get("reason") or "denied from mobile").strip()
    persist = bool(args.get("persist", False))
    try:
        from core_runtime.authority import get_authority_service
        service = get_authority_service()
        result = service.deny_request(request_id, reason=reason, persist=persist)
        return ok({"result": result})
    except Exception as exc:
        return error(str(exc), "DENY_FAILED")


def run(input_data, context=None):
    args = _merged(input_data)
    action = str(args.get("action") or "").strip().lower()
    handlers = {
        "list_events": list_events,
        "list_approvals": list_approvals,
        "approve": approve_approval,
        "deny": deny_approval,
    }
    handler = handlers.get(action)
    if handler is None:
        return error(f"unknown events action: {action}", "UNKNOWN_ACTION")
    return handler(input_data, context)
