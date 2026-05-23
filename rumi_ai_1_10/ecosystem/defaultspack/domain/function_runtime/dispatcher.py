from __future__ import annotations

import importlib
from typing import Any

from .errors import FunctionNotFoundError
from .registry import (
    MANAGEMENT_ALIASES,
    TOOL_FUNCTION_ACTIONS,
    block_module_for,
    default_args_for,
    get_spec,
)
from .response import error, normalize_exception, normalize_output, ok
from .schemas import ensure_dict


def run_defaultspack_function(
    function_id: str,
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        args = ensure_dict(input_data)
        ctx = dict(context or {})
        handler = get_handler(function_id)
        return normalize_output(handler(args, ctx))
    except FunctionNotFoundError as exc:
        return error(str(exc), "FUNCTION_NOT_FOUND")
    except Exception as exc:
        return normalize_exception(exc)


def get_handler(function_id: str):
    if function_id in _PROMPT_HANDLERS:
        return _PROMPT_HANDLERS[function_id]
    if function_id in _MODEL_RUNTIME_HANDLERS:
        return _MODEL_RUNTIME_HANDLERS[function_id]
    if function_id in TOOL_FUNCTION_ACTIONS:
        return lambda args, ctx: _run_tool_function(function_id, args, ctx)
    if function_id in MANAGEMENT_ALIASES:
        return lambda args, ctx: _run_existing_pack_function(MANAGEMENT_ALIASES[function_id], args, ctx)
    block_module = block_module_for(function_id)
    if block_module:
        return lambda args, ctx: _run_block_function(function_id, block_module, args, ctx)
    if get_spec(function_id) is not None:
        return lambda args, ctx: error(
            f"defaultspack:{function_id} is registered but has no implementation yet",
            "NOT_IMPLEMENTED",
        )
    raise FunctionNotFoundError(f"No handler registered for defaultspack:{function_id}")


def _run_block_function(
    function_id: str,
    block_module: str,
    args: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    payload = default_args_for(function_id)
    payload.update(args)
    payload = _apply_function_defaults(function_id, payload)
    module = importlib.import_module(block_module)
    run = getattr(module, "run")
    call_context = dict(context)
    call_context["_defaultspack_function_dispatch"] = True
    call_context["function_id"] = function_id
    return run(payload, call_context)


def _run_existing_pack_function(
    existing_function_id: str,
    args: dict[str, Any],
    context: dict[str, Any],
) -> Any:
    from core_runtime.pack_function_runtime import invoke_pack_function

    return invoke_pack_function("defaultspack", existing_function_id, args, context)


def _run_tool_function(
    function_id: str,
    args: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    from domain.tool.executor import ToolExecutor

    tool_name, defaults = TOOL_FUNCTION_ACTIONS[function_id]
    arguments = dict(defaults)
    if tool_name == "browser_computer":
        payload = dict(args.get("payload") or {})
        for key, value in args.items():
            if key not in {"action", "payload"}:
                payload[key] = value
        if payload:
            arguments["payload"] = payload
        if "action" in args:
            arguments["action"] = args["action"]
    else:
        arguments.update(args)
    # The public function is the safety boundary; call the local implementation
    # directly here to avoid recursing through the AI tool facade.
    result = ToolExecutor()._execute_local(tool_name, arguments, context)
    if function_id in {"browser_open_url", "browser_screenshot", "browser_session"} and isinstance(result, dict):
        try:
            from domain.browser.browser_artifacts import BrowserArtifactStore
            from domain.safety.audit import record_execution

            action = str(arguments.get("action") or result.get("action") or function_id)
            artifact = BrowserArtifactStore().record(action, result)
            result = {**result, "browser_artifact": artifact}
            record_execution(
                "browser.artifact",
                "medium",
                {"action": action, "url": result.get("url")},
                artifact_id=artifact.get("artifact_id"),
                session_id=artifact.get("session_id"),
            )
        except Exception:
            pass
    return ok(result)


def _apply_function_defaults(function_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if function_id == "ui_settings_get":
        payload.setdefault("_method", "GET")
    elif function_id == "ui_settings_update":
        payload.setdefault("_method", "PUT")
    elif function_id == "prompt_system_get":
        payload.setdefault("_method", "GET")
    elif function_id == "prompt_system_set":
        payload.setdefault("_method", "PUT")
    elif function_id == "coding_git_branch_get":
        payload.setdefault("_method", "GET")
    elif function_id == "coding_git_branch_create":
        payload.setdefault("_method", "POST")
    elif function_id == "coding_checkpoint_list":
        payload.setdefault("_method", "GET")
    elif function_id == "coding_checkpoint_create":
        payload.setdefault("_method", "POST")
    return payload


def _model_runtime_service():
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

    return ModelRuntimeSettingsService()


def _provider_key_status(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del args, context
    from domain.ai_client.api_key_store import provider_key_status

    return ok({"providers": provider_key_status()})


def _set_provider_key(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    from domain.ai_client.api_key_store import set_provider_api_key

    result = set_provider_api_key(
        str(args.get("provider_id") or "").strip(),
        str(args.get("value") or ""),
        api_id=args.get("api_id"),
        name=args.get("name"),
        base_url=args.get("base_url"),
        allowed_models=args.get("allowed_models"),
        default_model=args.get("default_model"),
        notes=args.get("notes"),
        quota_label=args.get("quota_label"),
    )
    if not result.get("success"):
        return error(result.get("error") or "failed to save api key", "API_KEY_SAVE_FAILED")
    return ok({key: value for key, value in result.items() if key != "error"})


def _delete_provider_key(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    from domain.ai_client.api_key_store import delete_provider_api_key

    result = delete_provider_api_key(
        str(args.get("provider_id") or "").strip(),
        str(args.get("api_id") or "").strip(),
    )
    if not result.get("success"):
        return error(result.get("error") or "failed to delete api key", "API_KEY_DELETE_FAILED")
    return ok({key: value for key, value in result.items() if key != "error"})


def _rename_provider_key(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    from domain.ai_client.api_key_store import rename_provider_api_key

    result = rename_provider_api_key(
        str(args.get("provider_id") or "").strip(),
        str(args.get("api_id") or "").strip(),
        str(args.get("name") or args.get("new_name") or "").strip(),
        new_api_id=args.get("new_api_id"),
        base_url=args.get("base_url"),
        allowed_models=args.get("allowed_models"),
        default_model=args.get("default_model"),
        notes=args.get("notes"),
        quota_label=args.get("quota_label"),
    )
    if not result.get("success"):
        return error(result.get("error") or "failed to rename api key", "API_KEY_RENAME_FAILED")
    return ok({key: value for key, value in result.items() if key != "error"})


def _validate_model_params(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    service = _model_runtime_service()
    level = args.get("thinking_level") or args.get("level")
    if level is not None:
        validation = service.validate_thinking_level(str(level), args.get("profile_id"))
        if not validation.get("valid"):
            return error(validation.get("message", "invalid thinking level"), "INVALID_INPUT", details=validation)
    return ok({"valid": True})


def _validate_prompt_template(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    from domain.prompt.effective import validate_prompt_template

    return ok(validate_prompt_template(args))


def _resolve_prompt_for_conversation(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    from domain.prompt.effective import resolve_prompt_for_conversation

    return ok(resolve_prompt_for_conversation(args, context))


def _model_call(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    from domain.ai_client.model_call import call_model

    result = call_model(args, context, call_handler=context.get("call_handler") if isinstance(context, dict) else None)
    if result.get("status") == "error":
        return error(str(result.get("error") or "model.call failed"), str(result.get("code") or "MODEL_CALL_FAILED"))
    return ok(result)


def _input_endpoint_create(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    import os
    import time

    from domain.external.token_store import set_external_token
    from domain.webhook.endpoint_store import WebhookEndpointStore

    shared_secret = str(args.get("shared_secret") or args.get("secret") or "").strip()
    if not shared_secret:
        return error("shared_secret is required", "INVALID_INPUT")
    ttl_seconds = args.get("ttl_seconds")
    try:
        ttl_value = int(ttl_seconds) if ttl_seconds not in (None, "") else 3600
    except (TypeError, ValueError):
        ttl_value = 3600
    ttl_value = max(ttl_value, 1)
    payload = {
        "id": str(args.get("endpoint_id") or args.get("id") or "").strip(),
        "kind": str(args.get("kind") or "generic").strip() or "generic",
        "input_profile_id": str(args.get("input_profile_id") or "generic.webhook.default").strip() or "generic.webhook.default",
        "enabled": args.get("enabled", True) is not False,
        "target": dict(args.get("target") if isinstance(args.get("target"), dict) else {}),
        "default_delivery": dict(args.get("default_delivery") if isinstance(args.get("default_delivery"), dict) else {"action_id": str(args.get("action_id") or "chat.message")}),
        "allowed_delivery_actions": args.get("allowed_delivery_actions") if isinstance(args.get("allowed_delivery_actions"), list) else [str(args.get("action_id") or "chat.message").strip()] if str(args.get("action_id") or "").strip() else [],
        "ttl_seconds": ttl_value,
        "expires_at": int(time.time() * 1000) + ttl_value * 1000,
        "security": {
            "mode": "shared_secret",
            "header": str(args.get("header") or "x-rumi-webhook-token").strip() or "x-rumi-webhook-token",
        },
        "metadata": dict(args.get("metadata") if isinstance(args.get("metadata"), dict) else {}),
    }
    created = WebhookEndpointStore().upsert(payload)
    endpoint = created.get("endpoint") if isinstance(created.get("endpoint"), dict) else {}
    endpoint_id = str(endpoint.get("id") or "")
    if endpoint_id:
        set_external_token("generic", shared_secret, token_id=endpoint_id, kind="webhook_shared_secret")
    port = int(os.environ.get("DEFAULTS_HTTP_PORT", "8766"))
    localhost_url = "http://localhost:{}/api/webhooks/inbound/{}".format(port, endpoint_id)
    return ok(
        {
            "endpoint": endpoint,
            "endpoint_id": endpoint_id,
            "localhost_url": localhost_url,
            "shared_secret": shared_secret,
            "ttl_seconds": ttl_value,
        }
    )


def _input_endpoint_delete(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    from domain.external.token_store import delete_external_token
    from domain.webhook.endpoint_store import WebhookEndpointStore

    endpoint_id = str(args.get("endpoint_id") or args.get("id") or "").strip()
    if not endpoint_id:
        return error("endpoint_id is required", "INVALID_INPUT")
    deleted = WebhookEndpointStore().delete(endpoint_id)
    delete_external_token("generic", endpoint_id)
    return ok(deleted)


def _input_endpoint_list(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del args, context
    import os

    from domain.webhook.endpoint_store import WebhookEndpointStore

    port = int(os.environ.get("DEFAULTS_HTTP_PORT", "8766"))
    endpoints = []
    for endpoint in WebhookEndpointStore().list_endpoints():
        item = dict(endpoint)
        item["localhost_url"] = "http://localhost:{}/api/webhooks/inbound/{}".format(port, item.get("id"))
        endpoints.append(item)
    return ok({"endpoints": endpoints})


_PROMPT_HANDLERS = {
    "prompt_validate_template": _validate_prompt_template,
    "prompt_resolve_for_conversation": _resolve_prompt_for_conversation,
}


_MODEL_RUNTIME_HANDLERS = {
    "ai_model_call": _model_call,
    "ai_get_preferred_model": lambda args, ctx: ok({"profile_id": _model_runtime_service().get_preferred_model()}),
    "ai_set_preferred_model": lambda args, ctx: ok(_model_runtime_service().set_preferred_model(str(args.get("profile_id") or args.get("model") or ""))),
    "ai_get_thinking_level": lambda args, ctx: ok(_model_runtime_service().get_thinking_level(args.get("scope", "global"), args.get("profile_id"), args.get("conversation_id"))),
    "ai_set_thinking_level": lambda args, ctx: ok(_model_runtime_service().set_thinking_level(str(args.get("level") or ""), args.get("scope", "global"), args.get("profile_id"), args.get("conversation_id"))),
    "ai_get_effective_thinking_level": lambda args, ctx: ok(_model_runtime_service().get_effective_thinking_level(args.get("profile_id"), args.get("conversation_id"))),
    "ai_normalize_thinking_level": lambda args, ctx: ok(_model_runtime_service().normalize_for_provider(str(args.get("provider_id") or ""), str(args.get("model_id") or args.get("model") or ""), str(args.get("level") or args.get("thinking_level") or ""))),
    "ai_validate_model_params": _validate_model_params,
    "ai_get_provider_key_status": _provider_key_status,
    "ai_set_provider_key": _set_provider_key,
    "ai_delete_provider_key": _delete_provider_key,
    "ai_rename_provider_key": _rename_provider_key,
    "input_endpoint_create": _input_endpoint_create,
    "input_endpoint_delete": _input_endpoint_delete,
    "input_endpoint_list": _input_endpoint_list,
}
