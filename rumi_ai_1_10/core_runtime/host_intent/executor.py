"""HostIntent prepare/approval executor.

This module intentionally does not touch host APIs. It validates JSON intents and
routes them through Authority. Actual host mediation belongs to the Viewer/host
capability broker.
"""

from __future__ import annotations

from typing import Any

from core_runtime.authority import get_authority_service

from .approval import check_host_intent_authority
from .models import is_host_intent_payload
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


def _authority_followup_for_operation(context: dict[str, Any], operation: str) -> tuple[str | None, str | None]:
    authority = context.get("authority") if isinstance(context.get("authority"), dict) else {}
    approvals = authority.get("approvals") or authority.get("approval_tokens")
    if isinstance(approvals, list):
        for item in approvals:
            if not isinstance(item, dict):
                continue
            if str(item.get("permission_id") or "").strip() == operation:
                return str(item.get("request_id") or "") or None, str(item.get("approval_token") or "") or None
    if str(authority.get("permission_id") or "").strip() == operation:
        return str(authority.get("request_id") or "") or None, str(authority.get("approval_token") or "") or None
    return None, None
