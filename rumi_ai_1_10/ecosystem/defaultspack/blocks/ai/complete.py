import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error, gen_id
from domain.ai_client.gateway import LLMGateway
from domain.ai_client.client import AuthorityApprovalRequired
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.dev.inspector import Inspector
from domain.prompt.manager import get_manager
from domain.temporal_context import add_temporal_context_message, current_datetime_context


def _authority_context_from_runtime(context, input_data):
    if not isinstance(context, dict):
        context = {}
    if not isinstance(input_data, dict):
        input_data = {}
    authority = context.get("authority") if isinstance(context.get("authority"), dict) else {}
    result = dict(authority)
    trusted_profile_id = str(result.get("profile_id") or context.get("profile_id") or "").strip()
    profile_id = trusted_profile_id or str(input_data.get("profile_id") or "").strip()
    if profile_id:
        result["profile_id"] = profile_id
    for key in ("conversation_id", "node_id", "graph_id"):
        value = str(result.get(key) or context.get(key) or input_data.get(key) or "").strip()
        if value:
            result[key] = value
    principal_id = str(
        result.get("principal_id")
        or context.get("principal_id")
        or context.get("authority_principal_id")
        or ""
    ).strip()
    if not principal_id and trusted_profile_id:
        principal_id = "profile:" + trusted_profile_id
    if principal_id:
        result["principal_id"] = principal_id
    return {key: value for key, value in result.items() if value not in ("", None)}


def run(input_data, context):
    model = input_data.get("model")
    messages = input_data.get("messages")
    if not model:
        return error("model is required", "MISSING_PARAM")
    if not messages:
        return error("messages is required", "MISSING_PARAM")
    messages = list(messages)
    tools = input_data.get("tools", [])
    params = dict(input_data.get("params") or {})
    if "thinking_level" not in params:
        params["thinking_level"] = ModelRuntimeSettingsService().get_effective_thinking_level(
            profile_id=model,
            conversation_id=input_data.get("conversation_id"),
        )["level"]

    # P1-4: Inspector 用のリクエストID を生成
    temporal_context = current_datetime_context(
        {
            **(context if isinstance(context, dict) else {}),
            **(input_data if isinstance(input_data, dict) else {}),
            **params,
        }
    )
    add_temporal_context_message(
        messages,
        context if isinstance(context, dict) else {},
        temporal_context=temporal_context,
    )
    request_id = gen_id()

    try:
        request = {"model": model, "messages": messages, "tools": tools, "params": params}
        if "_authority_context" not in params:
            authority_context = _authority_context_from_runtime(context, input_data)
            if authority_context:
                request["authority_context"] = authority_context
        result = LLMGateway().complete(request)
    except AuthorityApprovalRequired as e:
        return error(
            str(e) or "authority approval required",
            "AUTHORITY_APPROVAL_REQUIRED",
            details=_authority_approval_details(e),
        )
    except RuntimeError as e:
        return error(str(e), "PROVIDER_ERROR")

    # P1-4: Inspector にリクエストログを記録
    try:
        inspector = Inspector()
        manager = get_manager()
        system_prompt = manager.get_system_prompt()

        # メッセージからシステムプロンプトを抽出（もしあれば）
        prompt_used = system_prompt
        for msg in messages:
            if msg.get("role") == "system":
                prompt_used = msg.get("content", system_prompt)
                break

        # 使用されたツール名を抽出
        tools_called = []
        if tools:
            for t in tools:
                if isinstance(t, dict):
                    tool_name = t.get("name", t.get("function", {}).get("name", ""))
                    if tool_name:
                        tools_called.append(tool_name)
                elif isinstance(t, str):
                    tools_called.append(t)

        conversation_id = input_data.get("conversation_id", "")

        inspector.log_request(
            request_id=request_id,
            conversation_id=conversation_id,
            model=model,
            prompt_used=prompt_used,
            tools_called=tools_called,
            context_info={
                "message_count": len(messages),
                "source": "blocks.ai.complete",
                "params": params,
            },
        )
    except Exception:
        pass  # Inspector のエラーで本来の処理を止めない

    return ok(result)


def _authority_approval_details(exc):
    decision = getattr(exc, "decision", None)
    if decision is None:
        return {
            "status": "authority_approval_required",
            "approval_required": True,
            "requires_approval": True,
            "finish_reason": "authority_approval_required",
        }
    if callable(getattr(decision, "to_approval_event", None)):
        details = dict(decision.to_approval_event())
    elif callable(getattr(decision, "to_dict", None)):
        details = dict(decision.to_dict())
    else:
        details = {}
    details.setdefault("status", "authority_approval_required")
    details.setdefault("approval_required", True)
    details.setdefault("requires_approval", True)
    details.setdefault("finish_reason", "authority_approval_required")
    return details
