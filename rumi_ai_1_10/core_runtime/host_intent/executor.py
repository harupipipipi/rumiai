"""HostIntent prepare/approval executor.

This module intentionally does not touch host APIs. It validates JSON intents and
routes them through Authority. Actual host mediation belongs to the Viewer/host
capability broker.
"""

from __future__ import annotations

import importlib
import time
from typing import Any

from core_runtime.authority import get_authority_service

from .approval import check_host_intent_authority
from .models import HostIntent, is_host_intent_payload
from .validator import validate_host_intent


class HostIntentExecutor:
    def handle(
        self,
        payload: dict[str, Any],
        *,
        principal_id: str,
        caller_pack_id: str,
        caller_function_id: str,
        request_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = request_context if isinstance(request_context, dict) else {}
        validation = validate_host_intent(
            payload,
            caller_pack_id=caller_pack_id,
            caller_function_id=caller_function_id,
            conversation_id=str(context.get("conversation_id") or ""),
        )
        if not validation.ok or validation.intent is None:
            return {
                "status": "error",
                "success": False,
                "error_type": "host_intent_invalid",
                "errors": validation.errors,
            }
        intent = validation.intent
        request_id, approval_token = _authority_followup_for_operation(context, intent.operation)
        authority = check_host_intent_authority(
            get_authority_service(),
            intent,
            principal_id=principal_id,
            request_id=request_id,
            approval_token=approval_token,
        )
        if authority.get("approval_required"):
            return {
                "status": "approval_required",
                "success": False,
                "host_intent": intent.to_dict(),
                "authority": authority,
                **authority,
            }
        if not authority.get("allowed"):
            return {
                "status": "denied",
                "success": False,
                "error_type": "host_intent_denied",
                "host_intent": intent.to_dict(),
                "authority": authority,
            }
        brokered = _dispatch_to_viewer_broker(intent, request_id=request_id)
        if brokered is not None:
            return {
                "host_intent": intent.to_dict(),
                "authority": authority,
                **brokered,
            }
        return {
            "status": "prepared",
            "success": True,
            "host_intent": intent.to_dict(),
            "authority": authority,
            "message": "Host intent is approved and ready for host capability broker execution.",
        }


def maybe_handle_host_intent_output(
    output: Any,
    *,
    principal_id: str,
    caller_pack_id: str,
    caller_function_id: str,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not is_host_intent_payload(output):
        return None
    return HostIntentExecutor().handle(
        output,
        principal_id=principal_id,
        caller_pack_id=caller_pack_id,
        caller_function_id=caller_function_id,
        request_context=request_context,
    )


def _dispatch_to_viewer_broker(intent: HostIntent, *, request_id: str | None = None) -> dict[str, Any] | None:
    try:
        broker_client_module = importlib.import_module(
            _defaultspack_module("domain", "host_bridge", "viewer_broker_client")
        )
        approval = importlib.import_module(_defaultspack_module("domain", "safety", "approval"))
    except Exception as exc:
        return _host_broker_initialization_failed("broker_modules_import_failed", exc)

    ViewerBrokerClient = getattr(broker_client_module, "ViewerBrokerClient", None)
    from_environment = getattr(ViewerBrokerClient, "from_environment", None)
    issue_execution_token = getattr(approval, "issue_execution_token", None)
    if ViewerBrokerClient is None or not callable(from_environment):
        return _host_broker_initialization_failed("viewer_broker_client_missing")
    if not callable(issue_execution_token):
        return _host_broker_initialization_failed("approval_token_issuer_missing")
    try:
        client = from_environment()
        broker_available = bool(client.available())
    except Exception as exc:
        return _host_broker_initialization_failed("viewer_broker_client_initialization_failed", exc)
    if not broker_available:
        return {
            "status": "host_broker_unavailable",
            "success": False,
            "error_type": "host_broker_unavailable",
            "host_broker": {"available": False},
            "message": "Host intent is approved, but Rumi Viewer host broker is unavailable.",
        }

    try:
        execution_token = issue_execution_token(
            request_id or f"host_intent:{intent.operation}:{intent.args_hash[:12]}",
            intent.args_hash,
            expires_at=int(time.time()) + 300,
            operation=intent.operation,
            function_id=intent.host_function_id or intent.operation,
            pack_id=intent.caller_pack_id,
            conversation_id=intent.conversation_id,
        )
    except Exception as exc:
        return _host_broker_initialization_failed("approval_token_issue_failed", exc)
    payload = intent.to_dict()
    payload["approval_token"] = execution_token
    try:
        broker_response = client.start_stream(payload) if intent.is_stream else client.execute_intent(payload)
    except Exception as exc:
        return {
            "status": "host_broker_error",
            "success": False,
            "error_type": "host_broker_error",
            "host_broker": {"available": True, "error": str(exc)},
        }

    success = bool(isinstance(broker_response, dict) and broker_response.get("ok") is True)
    return {
        "status": "executed" if success else "host_broker_error",
        "success": success,
        "error_type": None if success else "host_broker_error",
        "host_broker": broker_response if isinstance(broker_response, dict) else {},
    }


def _host_broker_initialization_failed(reason: str, exc: Exception | None = None) -> dict[str, Any]:
    host_broker: dict[str, Any] = {"available": False, "initialization_error": reason}
    if exc is not None:
        host_broker["error"] = str(exc)
    return {
        "status": "host_broker_initialization_failed",
        "success": False,
        "error_type": "host_broker_initialization_failed",
        "host_broker": host_broker,
        "message": "Host intent is approved, but Rumi Viewer host broker could not be initialized.",
    }


def _defaultspack_module(*parts: str) -> str:
    return ".".join(("ecosystem", "defaultspack", *parts))


def _authority_followup_for_operation(context: dict[str, Any], operation: str) -> tuple[str | None, str | None]:
    raw_authority = context.get("authority")
    authority: dict[str, Any] = raw_authority if isinstance(raw_authority, dict) else {}
    approvals = authority.get("approvals") or authority.get("approval_tokens")
    if isinstance(approvals, dict):
        item = approvals.get(operation)
        if isinstance(item, dict):
            return str(item.get("request_id") or "") or None, str(item.get("approval_token") or "") or None
    if isinstance(approvals, list):
        for item in approvals:
            if not isinstance(item, dict):
                continue
            if str(item.get("permission_id") or "").strip() == operation:
                return str(item.get("request_id") or "") or None, str(item.get("approval_token") or "") or None
    if str(authority.get("permission_id") or "").strip() == operation:
        return str(authority.get("request_id") or "") or None, str(authority.get("approval_token") or "") or None
    return None, None
