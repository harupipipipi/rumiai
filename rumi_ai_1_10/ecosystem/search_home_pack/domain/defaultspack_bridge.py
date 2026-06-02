from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable

from core_runtime.paths import BASE_DIR

from .route_decision import RouteDecision, google_search_url
from .safe_url import classify_direct_url


FunctionInvoker = Callable[[str, dict[str, Any], dict[str, Any] | None, float | None], dict[str, Any]]

_FUNCTION_ALIASES = (
    "defaultspack.ai.model_call",
    "defaultspack.chat.create_conversation",
    "defaultspack.chat.send",
    "defaultspack.chat.stream",
    "defaultspack.tool.web_search",
)
_CLASSIFIER_PROMPT = """You are the route classifier for Rumi Search Home.

Routes:
- URL_NAVIGATE: direct URL or domain navigation only.
- GOOGLE_REDIRECT: user wants a web results page or a site/page search.
- ASK_AI: user wants an answer, explanation, reasoning, writing, coding help, or troubleshooting.
- ASK_AI_WITH_SEARCH: user wants an answer and likely needs fresh or external information such as news, stocks, prices, recent events, schedules, GitHub state, product facts, or recommendations.
- BLOCKED: unsafe URL scheme.

Prefer ASK_AI_WITH_SEARCH over GOOGLE_REDIRECT for question-like searches.
Return JSON only:
{
  "route": "...",
  "confidence": 0.0,
  "normalized_query": "...",
  "target_url": null,
  "reason": "...",
  "needs_freshness": true,
  "is_question_like": true
}
"""


class DefaultspackBridge:
    def __init__(
        self,
        *,
        invoker: FunctionInvoker | None = None,
        principal_id: str = "search_home_pack",
    ) -> None:
        self._invoker = invoker or self._default_invoke
        self._principal_id = principal_id

    def classify_with_ai(self, query: str) -> RouteDecision:
        result = self._invoke_ok(
            "defaultspack.ai.model_call",
            {
                "question": f"{_CLASSIFIER_PROMPT}\n\nUser input:\n{query}",
                "required_capabilities": ["model.fast"],
                "output_schema": {"type": "object"},
                "max_tokens": 400,
            },
            context={"source": "search_home.classifier"},
            timeout_seconds=45.0,
        )
        payload = self._extract_payload(result)
        output = payload.get("output")
        if isinstance(output, str):
            output = json.loads(output)
        if not isinstance(output, dict):
            raise RuntimeError("defaultspack.ai.model_call returned a non-object classifier payload")

        route = str(output.get("route") or "").strip() or "ASK_AI_WITH_SEARCH"
        normalized_query = str(output.get("normalized_query") or query).strip() or query.strip()
        confidence = _bounded_confidence(output.get("confidence"), fallback=0.5)
        target_url = output.get("target_url")
        reason = str(output.get("reason") or "AI classifier decision").strip()

        if route == "GOOGLE_REDIRECT" and not target_url:
            target_url = google_search_url(normalized_query)
        if route == "URL_NAVIGATE" and not target_url:
            direct_url = classify_direct_url(normalized_query)
            if direct_url and not direct_url.get("blocked"):
                target_url = str(direct_url["url"])
            else:
                route = "ASK_AI_WITH_SEARCH"
                reason = "AI classifier requested navigation without a valid direct URL"
                confidence = min(confidence, 0.55)
                target_url = None

        if route not in {
            "URL_NAVIGATE",
            "GOOGLE_REDIRECT",
            "ASK_AI",
            "ASK_AI_WITH_SEARCH",
            "BLOCKED",
        }:
            route = "ASK_AI_WITH_SEARCH"
            confidence = min(confidence, 0.55)
            reason = "AI classifier returned an unknown route"

        return RouteDecision(
            route=route,
            confidence=confidence,
            normalized_query=normalized_query,
            target_url=str(target_url) if isinstance(target_url, str) else None,
            reason=reason,
            source="ai",
        )

    def ask_ai(self, query: str, *, with_search: bool) -> dict[str, Any]:
        conversation = self._invoke_ok(
            "defaultspack.chat.create_conversation",
            {
                "conversation_kind": "search_home",
                "tags": ["search_home"],
                "metadata": {
                    "source": "search_home",
                    "search_home": True,
                    "requires_freshness": with_search,
                },
            },
            context={"source": "search_home.chat"},
            timeout_seconds=30.0,
        )
        conversation_id = str(conversation.get("id") or conversation.get("conversation_id") or "").strip()
        if not conversation_id:
            raise RuntimeError("defaultspack.chat.create_conversation did not return a conversation id")

        params: dict[str, Any] = {}
        if with_search:
            params["tool_policy"] = {
                "selected_tools": ["web_search"],
                "allowed_tools": ["web_search"],
                "tool_choice": "auto",
            }

        message = self._invoke_ok(
            "defaultspack.chat.send",
            {
                "conversation_id": conversation_id,
                "message": {
                    "role": "user",
                    "content": query,
                    "metadata": {
                        "source": "search_home",
                        "search_home": True,
                        "requires_freshness": with_search,
                    },
                },
                "params": params,
            },
            context={"source": "search_home.chat", "conversation_id": conversation_id},
            timeout_seconds=180.0,
        )
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        routing = metadata.get("model_routing") if isinstance(metadata.get("model_routing"), dict) else {}
        used_tools = _used_tool_names(message.get("tool_logs"))
        model = str(message.get("model") or routing.get("selected_model") or "").strip() or None
        return {
            "status": "ok",
            "conversation_id": conversation_id,
            "answer": _message_text(message),
            "message": message,
            "model": model,
            "used_tools": used_tools,
            "routing": routing,
        }

    def healthcheck(self) -> dict[str, Any]:
        alias_status = {alias: self._is_function_available(alias) for alias in _FUNCTION_ALIASES}
        return {
            "status": "ok",
            "principal_id": self._principal_id,
            "aliases": alias_status,
        }

    def _default_invoke(
        self,
        qualified_name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        from core_runtime.capability_executor import get_capability_executor
        from core_runtime.di_container import get_container

        container = get_container()
        registry = container.get_or_none("function_registry")
        if registry is not None:
            self._ensure_pack_functions_registered(registry, _pack_id_from_name(qualified_name), qualified_name)
        executor = container.get_or_none("capability_executor") or get_capability_executor()
        request = {
            "type": "function.call",
            "qualified_name": qualified_name,
            "args": dict(args or {}),
            "context": dict(context or {}),
            "request_id": str((context or {}).get("request_id") or uuid.uuid4()),
        }
        if timeout_seconds is not None:
            request["timeout_seconds"] = timeout_seconds
        response = executor.execute(self._principal_id, request)
        if not getattr(response, "success", False):
            error_type = str(getattr(response, "error_type", None) or "FUNCTION_CALL_FAILED").upper()
            return {
                "status": "error",
                "error": {
                    "code": error_type,
                    "message": str(getattr(response, "error", None) or "Function call failed"),
                },
            }
        output = getattr(response, "output", None)
        if isinstance(output, dict):
            return output if output.get("status") in {"ok", "error"} else {"status": "ok", "data": output}
        return {"status": "ok", "data": output}

    def _invoke_ok(
        self,
        qualified_name: str,
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        result = self._invoker(qualified_name, dict(args or {}), dict(context or {}), timeout_seconds)
        if not isinstance(result, dict):
            raise RuntimeError(f"{qualified_name} returned a non-dict result")
        if result.get("status") != "ok":
            error = result.get("error")
            if isinstance(error, dict):
                raise RuntimeError(str(error.get("message") or f"{qualified_name} failed"))
            raise RuntimeError(str(error or f"{qualified_name} failed"))
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return {"value": data}

    def _extract_payload(self, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("status") == "ok" and isinstance(value.get("data"), dict):
            return dict(value["data"])
        return dict(value)

    def _is_function_available(self, alias: str) -> bool:
        try:
            from core_runtime.di_container import get_container

            registry = get_container().get_or_none("function_registry")
            if registry is None:
                return False
            self._ensure_pack_functions_registered(registry, _pack_id_from_name(alias), alias)
            return registry.get(alias) is not None or registry.resolve_by_alias(alias) is not None
        except Exception:
            return False

    def _ensure_pack_functions_registered(self, registry: Any, pack_id: str, alias: str) -> None:
        if not pack_id:
            return
        try:
            if registry.get(alias) is not None:
                return
        except Exception:
            pass
        try:
            if registry.resolve_by_alias(alias) is not None:
                return
        except Exception:
            pass

        functions_root = _functions_root_for(pack_id)
        if functions_root is None or not functions_root.is_dir():
            return
        for function_dir in sorted(path for path in functions_root.iterdir() if path.is_dir()):
            manifest_path = function_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            function_id = str(manifest.get("function_id") or function_dir.name).strip()
            if not function_id:
                continue
            try:
                registry.register(
                    pack_id=pack_id,
                    function_id=function_id,
                    manifest=manifest,
                    function_dir=function_dir,
                )
            except Exception:
                continue


def _pack_id_from_name(qualified_name: str) -> str:
    if ":" in qualified_name:
        return qualified_name.split(":", 1)[0]
    if "." in qualified_name:
        return qualified_name.split(".", 1)[0]
    return ""


def _functions_root_for(pack_id: str) -> Path | None:
    for base_dir in _candidate_base_dirs():
        candidate = base_dir / "ecosystem" / pack_id / "functions"
        if candidate.is_dir():
            return candidate
    return None


def _candidate_base_dirs() -> list[Path]:
    raw_candidates = [Path(str(BASE_DIR))]
    for env_name in ("RUMI_APP_DIR", "RUMI_CORE_DIR", "REPO"):
        configured = os.environ.get(env_name)
        if configured:
            raw_candidates.append(Path(configured))
    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        if not str(candidate):
            continue
        for base in (candidate, candidate / "rumi_ai_1_10"):
            if not str(base):
                continue
            key = str(base.resolve()) if base.exists() else str(base)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(base)
    return resolved


def _bounded_confidence(raw: Any, *, fallback: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(value, 1.0))


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        text = "".join(parts).strip()
        if text:
            return text
    return str(message.get("raw_text") or "").strip()


def _used_tool_names(tool_logs: Any) -> list[str]:
    if not isinstance(tool_logs, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for log in tool_logs:
        if not isinstance(log, dict):
            continue
        name = str(log.get("tool_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
