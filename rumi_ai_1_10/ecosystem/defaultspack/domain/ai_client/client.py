import os
import sys
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ai_client.api_key_store import provider_api_metadata, provider_has_api_key, provider_named_api_keys, read_provider_api_key
from domain.ai_client.providers import (
    _cloud_runtime_enabled,
    build_profile_catalog,
    detect_available_providers,
    detect_rumi_provider,
    get_all_known_models,
    get_provider_catalog,
    get_provider_catalog_map,
)


class AIClient:
    """AI Client - provider routing with profile and catalog compatibility."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._providers = {}
        self._profiles = {}
        self._register_default_provider()
        self._auto_register_providers()
        self._auto_register_rumi()

    def _register_default_provider(self):
        from domain.ai_client.providers.stub_provider import StubProvider

        self._providers["stub"] = StubProvider()

    def _auto_register_providers(self):
        """環境変数が設定されているプロバイダーを自動登録する。"""
        try:
            available = detect_available_providers()
            provider_catalog = get_provider_catalog_map()
            cloud_enabled = _cloud_runtime_enabled()
            local_default_enabled = self._local_default_runtime_enabled()
            for name, instance in available.items():
                entry = provider_catalog.get(name, {})
                availability = entry.get("availability", {}) if isinstance(entry.get("availability"), dict) else {}
                if (
                    availability.get("configuration_source") == "default_local_endpoint"
                    and not local_default_enabled
                ):
                    continue
                if not cloud_enabled and entry.get("kind") not in {"builtin", "local"}:
                    if not provider_has_api_key(name):
                        continue
                self._providers[name] = instance
        except Exception:
            pass

    @staticmethod
    def _local_default_runtime_enabled():
        value = str(os.environ.get("RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS", "") or "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _auto_register_rumi(self):
        """rumi プロバイダーを自動登録する（他のプロバイダーが1つ以上ある場合のみ）。"""
        try:
            rumi = detect_rumi_provider(self)
            if rumi is not None:
                self._providers["rumi"] = rumi
        except Exception:
            pass

    def register_provider(self, name, provider):
        """プロバイダーを動的に登録する。"""
        self._providers[name] = provider

    def register_profile(self, name, profile=None, provider="", model="", **kwargs):
        """互換的にプロファイルを登録する。"""
        if isinstance(profile, dict):
            payload = dict(profile)
        else:
            payload = dict(kwargs)
            if profile is not None and not provider:
                provider = str(profile)
            if provider:
                payload["provider"] = provider
            if model:
                payload["model"] = model
        self._profiles[name] = payload

    def _active_provider_ids(self):
        return set(self._providers.keys())

    def _provider_model_candidates(self, provider_name):
        provider = self._providers.get(provider_name)
        if provider is None:
            return []
        listed = []
        if callable(getattr(provider, "list_models", None)):
            try:
                listed = provider.list_models() or []
            except Exception:
                listed = []
        if not listed and hasattr(provider, "KNOWN_MODELS"):
            listed = getattr(provider, "KNOWN_MODELS", []) or []
        return listed

    @staticmethod
    def _normalize_runtime_model(provider_id, provider_entry, raw):
        if isinstance(raw, str):
            model_id = raw.split("/", 1)[1] if "/" in raw else raw
            qualified_model_id = raw if "/" in raw else f"{provider_id}/{model_id}"
            display_name = model_id
            model_type = "chat"
            defaults = {}
            metadata = {}
            capabilities = []
            context_window = 0
            max_context = 0
            supports_thinking = False
            thinking_levels = []
        elif isinstance(raw, dict):
            qualified_model_id = str(raw.get("id", "")).strip()
            model_id = str(raw.get("model_id", "")).strip()
            if qualified_model_id and "/" in qualified_model_id and not model_id:
                _, model_id = qualified_model_id.split("/", 1)
            if not model_id:
                model_id = str(raw.get("model_name") or raw.get("name") or "").strip()
            if not model_id:
                return None
            if not qualified_model_id:
                qualified_model_id = f"{provider_id}/{model_id}"
            display_name = str(raw.get("display_name") or raw.get("name") or model_id)
            model_type = str(raw.get("type", "chat"))
            defaults = dict(raw.get("defaults", {}))
            metadata = dict(raw.get("metadata", {}))
            raw_capabilities = raw.get("capabilities", [])
            if isinstance(raw_capabilities, dict):
                capabilities = [key for key, value in raw_capabilities.items() if value]
                capability_map = dict(raw_capabilities)
            else:
                capabilities = list(raw_capabilities or [])
                capability_map = {str(key): True for key in capabilities}
            context_window = int(raw.get("context_window", raw.get("max_context", raw.get("max_context_tokens", 0))) or 0)
            max_context = int(raw.get("max_context", raw.get("max_context_tokens", context_window)) or 0)
            supports_thinking = bool(
                raw.get("supports_thinking")
                or capability_map.get("thinking")
                or capability_map.get("reasoning")
                or metadata.get("supports_thinking")
                or model_type == "reasoning"
            )
            thinking_levels = list(raw.get("thinking_levels") or metadata.get("thinking_levels") or [])
            if supports_thinking and not thinking_levels:
                thinking_levels = ["low", "medium", "high", "xhigh"]
        else:
            return None

        normalized = {
            "id": qualified_model_id,
            "qualified_model_id": qualified_model_id,
            "provider": provider_id,
            "provider_id": provider_id,
            "provider_display_name": provider_entry.get("display_name", provider_id),
            "model_id": model_id,
            "model_name": model_id,
            "name": display_name,
            "display_name": display_name,
            "type": model_type,
            "context_window": context_window,
            "max_context": max_context,
            "max_context_tokens": max_context,
            "supports_thinking": supports_thinking,
            "thinking_levels": thinking_levels,
            "default_thinking_level": raw.get("default_thinking_level", metadata.get("default_thinking_level", "medium" if supports_thinking else None)) if isinstance(raw, dict) else None,
            "capabilities": capabilities,
            "availability": dict(provider_entry.get("availability", {})),
            "supports_invoke": bool(
                provider_entry.get("availability", {}).get("supports_invoke", False)
            ),
            "defaults": defaults,
            "metadata": metadata,
        }
        normalized["metadata"].update(
            {
                "provider_model_key": qualified_model_id,
                "provider_display_name": provider_entry.get("display_name", provider_id),
                "provider_kind": provider_entry.get("kind", ""),
                "availability_status": provider_entry.get("availability", {}).get("status"),
                "max_context": max_context,
                "supports_thinking": supports_thinking,
                "thinking_levels": thinking_levels,
            }
        )
        return normalized

    def _runtime_model_matches(self, model_ref):
        active_provider_ids = self._active_provider_ids()
        catalog_map = get_provider_catalog_map(active_provider_ids=active_provider_ids)
        matches = []
        seen = set()
        for provider_id in active_provider_ids:
            provider_entry = catalog_map.get(provider_id, {})
            provider_entry.setdefault("display_name", provider_id)
            provider_entry.setdefault("availability", {"active": True, "supports_invoke": True})
            for raw in self._provider_model_candidates(provider_id):
                candidate = self._normalize_runtime_model(provider_id, provider_entry, raw)
                if candidate is None:
                    continue
                candidate_key = (candidate["provider_id"], candidate["model_id"])
                if candidate_key in seen:
                    continue
                seen.add(candidate_key)
                if model_ref in {
                    candidate["qualified_model_id"],
                    candidate["id"],
                    candidate["model_id"],
                    candidate["name"],
                    candidate["display_name"],
                }:
                    matches.append(candidate)
        return matches

    def resolve_provider(self, model_str):
        """model文字列("provider/model" or "profile_name")から解決する。"""
        if "/" in model_str:
            provider_name, model_name = model_str.split("/", 1)
        else:
            profile = self._profiles.get(model_str)
            if profile:
                provider_name = profile.get("provider") or profile.get("provider_id") or "stub"
                model_name = (
                    profile.get("model")
                    or profile.get("model_id")
                    or profile.get("qualified_model_id")
                    or model_str
                )
                if isinstance(model_name, str) and "/" in model_name:
                    resolved_provider, resolved_model = model_name.split("/", 1)
                    provider_name = provider_name or resolved_provider
                    model_name = resolved_model
            else:
                matches = []
                seen = set()
                for item in self.list_models():
                    item_key = (item.get("provider_id"), item.get("model_id"))
                    if item_key in seen:
                        continue
                    if model_str in {
                        item.get("model_id"),
                        item.get("qualified_model_id"),
                        item.get("id"),
                        item.get("name"),
                        item.get("display_name"),
                        item.get("disambiguated_name"),
                    }:
                        seen.add(item_key)
                        matches.append(item)
                for item in self._runtime_model_matches(model_str):
                    item_key = (item.get("provider_id"), item.get("model_id"))
                    if item_key not in seen:
                        seen.add(item_key)
                        matches.append(item)
                if len(matches) == 1:
                    provider_name = matches[0].get("provider_id", "stub")
                    model_name = matches[0].get("model_id", model_str)
                else:
                    provider_name = "stub"
                    model_name = model_str
        provider = self._providers.get(provider_name, self._providers["stub"])
        return provider, model_name

    def _settings_path(self):
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "frontend_settings.json"

    def _api_routes(self):
        data = self._settings_data()
        if not data:
            return {}
        models = data.get("models") if isinstance(data.get("models"), dict) else {}
        apis = data.get("apis") if isinstance(data.get("apis"), dict) else {}
        routes = {}
        for item in self._structured_api_routes(models.get("api_routes") or apis.get("api_routes")):
            model_ref = str(item.get("model") or "").strip()
            route_refs = [str(route).strip() for route in item.get("routes", []) if str(route).strip()]
            if model_ref and route_refs:
                routes[model_ref] = route_refs
        raw_routes = models.get("model_api_routes") or apis.get("model_api_routes") or ""
        if isinstance(raw_routes, list):
            raw_routes = "\n".join(str(item) for item in raw_routes)
        for raw_line in str(raw_routes or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^(.+?):\s+(.+)$", line)
            if not match:
                continue
            model_ref = match.group(1).strip()
            route_refs = [item.strip() for item in match.group(2).split(",") if item.strip()]
            if model_ref and route_refs:
                routes.setdefault(model_ref, route_refs)
        return routes

    def _settings_data(self):
        try:
            return json.loads(self._settings_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _jsonish(value, fallback):
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return fallback
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return fallback
        return value

    def _structured_api_routes(self, value):
        parsed = self._jsonish(value, [])
        if isinstance(parsed, dict):
            raw_items = [
                {"model": key, **(route if isinstance(route, dict) else {"routes": route})}
                for key, route in parsed.items()
            ]
        elif isinstance(parsed, list):
            raw_items = parsed
        else:
            raw_items = []
        routes = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            model_ref = str(item.get("model") or item.get("profile_id") or "").strip()
            raw_routes = item.get("routes", item.get("apis", item.get("api_refs", [])))
            if isinstance(raw_routes, str):
                route_refs = [part.strip() for part in raw_routes.split(",") if part.strip()]
            elif isinstance(raw_routes, list):
                route_refs = [str(part).strip() for part in raw_routes if str(part or "").strip()]
            else:
                route_refs = []
            if model_ref and route_refs:
                routes.append({"model": model_ref, "routes": route_refs})
        return routes

    def _routes_for_model(self, model):
        routes = self._api_routes()
        if model in routes:
            return routes[model]
        if isinstance(model, str) and "/" in model:
            model_id = model.split("/", 1)[1]
            return routes.get(model_id, [])
        return []

    @staticmethod
    def _route_parts(route_ref):
        cleaned = str(route_ref or "").strip()
        if "/" not in cleaned:
            return cleaned, "main"
        provider_id, api_id = cleaned.split("/", 1)
        return provider_id.strip(), api_id.strip() or "main"

    @staticmethod
    def _is_rate_limit_error(exc):
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "429",
                "rate limit",
                "rate_limit",
                "quota",
                "resource_exhausted",
                "provider_error",
                "provider error",
                "timeout",
                "timed out",
                "temporarily",
                "503",
                "502",
                "504",
            )
        )

    def _model_for_route(self, model, provider_id):
        if isinstance(model, str) and "/" in model:
            _, model_id = model.split("/", 1)
            return f"{provider_id}/{model_id}"
        return f"{provider_id}/{model}"

    @staticmethod
    def _provider_unconfigured_message(model):
        provider_name = "stub"
        if isinstance(model, str) and "/" in model:
            provider_name = model.split("/", 1)[0] or provider_name
        return (
            f"{provider_name}: provider is not configured. "
            "Configure a real or local AI provider before sending a message."
        )

    def _api_route_attempts(self, model, route_refs):
        attempts = []
        for route_ref in route_refs:
            provider_id, api_id = self._route_parts(route_ref)
            if not provider_id:
                continue
            api_key = read_provider_api_key(provider_id, api_id)
            if not api_key:
                continue
            route_model = self._model_for_route(model, provider_id)
            provider, model_name = self.resolve_provider(route_model)
            if provider.__class__.__name__ == "StubProvider":
                continue
            attempts.append((provider, model_name, api_key, provider_api_metadata(provider_id, api_id)))
        return attempts

    def _api_bound_profile_parts(self, model):
        if not isinstance(model, str) or "/" not in model:
            return None
        parts = model.split("/")
        if len(parts) < 3:
            return None
        provider_id = parts[0].strip()
        api_id = parts[1].strip()
        model_id = "/".join(parts[2:]).strip()
        if not provider_id or not api_id or not model_id:
            return None
        named_key = next(
            (
                item
                for item in provider_named_api_keys(provider_id)
                if str(item.get("api_id") or "").strip() == api_id and item.get("configured")
            ),
            None,
        )
        if not named_key:
            return None
        if not read_provider_api_key(provider_id, api_id):
            return None
        metadata = provider_api_metadata(provider_id, api_id)
        allowed = {str(item) for item in metadata.get("allowed_models", []) if str(item or "").strip()}
        if allowed and model_id not in allowed and f"{provider_id}/{model_id}" not in allowed:
            return None
        return provider_id, api_id, model_id, metadata

    def _call_api_bound_profile(self, method_name, model, messages, tools=None, params=None):
        parts = self._api_bound_profile_parts(model)
        if parts is None:
            return None, False
        provider_id, api_id, model_id, metadata = parts
        api_key = read_provider_api_key(provider_id, api_id)
        route_model = f"{provider_id}/{model_id}"
        provider, model_name = self.resolve_provider(route_model)
        if provider.__class__.__name__ == "StubProvider":
            return None, False
        if method_name == "stream":
            return self._stream_with_api_routes([(provider, model_name, api_key, metadata)], messages, tools, params), True
        return self._call_provider_with_overrides(provider, model_name, api_key, metadata, method_name, messages, tools, params), True

    def _call_provider_with_overrides(self, provider, model_name, api_key, metadata, method_name, messages, tools=None, params=None):
        previous_key = getattr(provider, "_api_key", None)
        previous_base_url = getattr(provider, "_base_url", None)
        previous_base_url_attr = getattr(provider, "BASE_URL", None)
        base_url = str((metadata or {}).get("base_url") or "").strip().rstrip("/")
        try:
            if previous_key is not None and api_key:
                provider._api_key = api_key
            if base_url and previous_base_url is not None:
                provider._base_url = base_url
                provider.BASE_URL = base_url
            method = getattr(provider, method_name)
            return method(model_name, messages, tools or [], params or {})
        finally:
            if previous_key is not None:
                provider._api_key = previous_key
            if previous_base_url is not None:
                provider._base_url = previous_base_url
                provider.BASE_URL = previous_base_url_attr

    def _call_with_api_routes(self, method_name, model, messages, tools=None, params=None):
        routed, handled = self._call_api_bound_profile(method_name, model, messages, tools, params)
        if handled:
            return routed, True
        route_refs = self._routes_for_model(model)
        if not route_refs:
            return None, False

        if method_name == "stream":
            route_attempts = self._api_route_attempts(model, route_refs)
            if not route_attempts:
                return None, False
            return self._stream_with_api_routes(route_attempts, messages, tools, params), True

        last_error = None
        for route_ref in route_refs:
            provider_id, api_id = self._route_parts(route_ref)
            if not provider_id:
                continue
            api_key = read_provider_api_key(provider_id, api_id)
            if not api_key:
                continue
            route_model = self._model_for_route(model, provider_id)
            provider, model_name = self.resolve_provider(route_model)
            if provider.__class__.__name__ == "StubProvider":
                continue
            metadata = provider_api_metadata(provider_id, api_id)
            try:
                return self._call_provider_with_overrides(provider, model_name, api_key, metadata, method_name, messages, tools, params), True
            except Exception as exc:
                last_error = exc
                if not self._is_rate_limit_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        return None, False

    def _stream_with_api_routes(self, route_attempts, messages, tools=None, params=None):
        last_error = None
        for provider, model_name, api_key, metadata in route_attempts:
            previous_key = getattr(provider, "_api_key", None)
            previous_base_url = getattr(provider, "_base_url", None)
            previous_base_url_attr = getattr(provider, "BASE_URL", None)
            base_url = str((metadata or {}).get("base_url") or "").strip().rstrip("/")
            yielded = False
            try:
                if previous_key is not None:
                    provider._api_key = api_key
                if base_url and previous_base_url is not None:
                    provider._base_url = base_url
                    provider.BASE_URL = base_url
                for chunk in provider.stream(model_name, messages, tools or [], params or {}):
                    yielded = True
                    yield chunk
                return
            except Exception as exc:
                last_error = exc
                if yielded or not self._is_rate_limit_error(exc):
                    raise
            finally:
                if previous_key is not None:
                    provider._api_key = previous_key
                if previous_base_url is not None:
                    provider._base_url = previous_base_url
                    provider.BASE_URL = previous_base_url_attr
        if last_error is not None:
            raise last_error

    def _composite_models(self):
        data = self._settings_data()
        models = data.get("models") if isinstance(data.get("models"), dict) else {}
        raw = self._jsonish(models.get("composite_models"), [])
        if isinstance(raw, dict):
            items = [{"id": key, **(value if isinstance(value, dict) else {})} for key, value in raw.items()]
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        composites = {}
        for item in items:
            if not isinstance(item, dict) or item.get("enabled", True) is False:
                continue
            composite_id = str(item.get("id") or item.get("profile_id") or item.get("name") or "").strip()
            if composite_id:
                composites[composite_id] = item
        return composites

    def _composite_for_model(self, model):
        if not isinstance(model, str):
            return None
        composites = self._composite_models()
        if model in composites:
            return composites[model]
        if "/" in model:
            tail = model.split("/", 1)[1]
            return composites.get(tail)
        return None

    def _complete_composite(self, composite, messages, tools=None, params=None):
        mode = str(composite.get("mode") or composite.get("type") or "fallback_chain")
        members = composite.get("members", composite.get("models", composite.get("chain", [])))
        if isinstance(members, str):
            members = [part.strip() for part in members.split(",") if part.strip()]
        if not isinstance(members, list) or not members:
            raise RuntimeError("composite model has no members")
        if mode == "ensemble":
            return self._complete_ensemble(composite, members, messages, tools, params)
        return self._complete_fallback_chain(members, messages, tools, params)

    def _member_model(self, member):
        if isinstance(member, dict):
            return str(member.get("model") or member.get("profile_id") or "").strip()
        return str(member or "").strip()

    def _complete_fallback_chain(self, members, messages, tools=None, params=None):
        last_error = None
        for member in members:
            model = self._member_model(member)
            if not model:
                continue
            if not self._member_conditions_match(member, messages, tools, params):
                continue
            try:
                next_params = dict(params or {})
                next_params["_composite_depth"] = int(next_params.get("_composite_depth", 0) or 0) + 1
                return self.complete(model, messages, tools or [], next_params)
            except Exception as exc:
                last_error = exc
                if not self._should_fallback_from_member_error(member, exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("composite fallback chain had no runnable members")

    def _member_conditions_match(self, member, messages, tools=None, params=None):
        if not isinstance(member, dict):
            return True
        conditions = member.get("conditions") or member.get("when") or {}
        if not isinstance(conditions, dict) or not conditions:
            return True
        has_images = self._messages_have_images(messages)
        has_tools = bool(tools)
        if "has_images" in conditions and bool(conditions.get("has_images")) != has_images:
            return False
        if "requires_vision" in conditions and bool(conditions.get("requires_vision")) != has_images:
            return False
        if "has_tools" in conditions and bool(conditions.get("has_tools")) != has_tools:
            return False
        if "requires_tools" in conditions and bool(conditions.get("requires_tools")) != has_tools:
            return False
        text_contains = conditions.get("text_contains") or conditions.get("contains")
        if text_contains and not self._condition_text_matches(text_contains, self._messages_text(messages)):
            return False
        task_types = conditions.get("task_types") or conditions.get("task_type")
        if task_types and not self._condition_task_type_matches(task_types, params or {}):
            return False
        return True

    def _should_fallback_from_member_error(self, member, exc):
        fallback_on = member.get("fallback_on") if isinstance(member, dict) else None
        values = self._fallback_on_values(fallback_on)
        if not values:
            return self._is_rate_limit_error(exc)
        if "*" in values or "any" in values or "all" in values:
            return True
        kind = self._error_kind(exc)
        aliases = {
            "429": "rate_limit",
            "rate_limit_error": "rate_limit",
            "rate-limit": "rate_limit",
            "quota_exceeded": "quota",
            "resource_exhausted": "quota",
            "provider error": "provider_error",
            "server_error": "provider_error",
            "5xx": "provider_error",
            "timed_out": "timeout",
        }
        normalized = {aliases.get(value, value) for value in values}
        return kind in normalized

    @staticmethod
    def _fallback_on_values(value):
        if isinstance(value, str):
            raw = re.split(r"[,\s]+", value)
        elif isinstance(value, list):
            raw = value
        else:
            raw = []
        return {str(item or "").strip().casefold() for item in raw if str(item or "").strip()}

    @staticmethod
    def _error_kind(exc):
        message = str(exc).casefold()
        if "429" in message or "rate limit" in message or "rate_limit" in message:
            return "rate_limit"
        if "quota" in message or "resource_exhausted" in message:
            return "quota"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if "401" in message or "403" in message or "unauthorized" in message or "forbidden" in message:
            return "unauthorized"
        if any(token in message for token in ("provider_error", "provider error", "502", "503", "504", "temporarily")):
            return "provider_error"
        return "unknown"

    @classmethod
    def _condition_text_matches(cls, expected, text):
        haystack = str(text or "").casefold()
        if isinstance(expected, str):
            needles = [expected]
        elif isinstance(expected, list):
            needles = expected
        else:
            return True
        needles = [str(item or "").strip().casefold() for item in needles if str(item or "").strip()]
        return not needles or any(needle in haystack for needle in needles)

    @staticmethod
    def _condition_task_type_matches(expected, params):
        hints = params.get("task_hints") if isinstance(params.get("task_hints"), dict) else {}
        actual = str(params.get("task_type") or hints.get("task_type") or hints.get("type") or "").strip().casefold()
        if not actual:
            return False
        if isinstance(expected, str):
            options = [expected]
        elif isinstance(expected, list):
            options = expected
        else:
            return True
        return actual in {str(item or "").strip().casefold() for item in options if str(item or "").strip()}

    @staticmethod
    def _messages_text(messages):
        parts = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text") or block.get("content") or ""))
        return "\n".join(parts)

    @staticmethod
    def _messages_have_images(messages):
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = str(block.get("type") or "").casefold()
                    mime = str(block.get("mime_type") or block.get("mime") or "").casefold()
                    if block_type in {"image", "image_url", "input_image"} or mime.startswith("image/"):
                        return True
        return False

    def _complete_ensemble(self, composite, members, messages, tools=None, params=None):
        member_models = [self._member_model(member) for member in members if self._member_model(member)]
        if not member_models:
            raise RuntimeError("composite ensemble has no runnable members")
        responses = []
        errors = []

        def call_member(model):
            next_params = dict(params or {})
            next_params["_composite_depth"] = int(next_params.get("_composite_depth", 0) or 0) + 1
            return model, self.complete(model, messages, tools or [], next_params)

        with ThreadPoolExecutor(max_workers=min(4, len(member_models))) as executor:
            futures = [executor.submit(call_member, model) for model in member_models]
            for future in as_completed(futures):
                try:
                    model, response = future.result()
                    responses.append({"model": model, "response": response, "text": self._response_text(response)})
                except Exception as exc:
                    errors.append(str(exc))
        if not responses:
            raise RuntimeError("all ensemble members failed: " + "; ".join(errors))
        merge_model = str(composite.get("merge_model") or composite.get("synthesizer_model") or "").strip()
        if merge_model:
            synthesis_prompt = [
                {
                    "role": "system",
                    "content": "Merge multiple model answers into one concise final answer. Preserve correct details and note uncertainty only when answers conflict.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "original_messages": messages,
                            "member_answers": [
                                {"model": item["model"], "answer": item["text"]}
                                for item in responses
                            ],
                            "member_errors": errors,
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            next_params = dict(params or {})
            next_params["_composite_depth"] = int(next_params.get("_composite_depth", 0) or 0) + 1
            merged = self.complete(merge_model, synthesis_prompt, [], next_params)
            metadata = dict(merged.get("metadata") or {}) if isinstance(merged, dict) else {}
            metadata["ensemble"] = {"members": [item["model"] for item in responses], "errors": errors}
            if isinstance(merged, dict):
                merged["metadata"] = metadata
            return merged
        return {
            "content": [
                {
                    "type": "text",
                    "text": "\n\n".join(f"[{item['model']}]\n{item['text']}" for item in responses),
                }
            ],
            "finish_reason": "ensemble",
            "usage": {},
            "metadata": {"ensemble": {"members": [item["model"] for item in responses], "errors": errors}},
        }

    @staticmethod
    def _response_text(response):
        if not isinstance(response, dict):
            return str(response or "")
        content = response.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text") or block.get("content") or ""))
                else:
                    parts.append(str(block))
            return "\n".join(part for part in parts if part)
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(message, dict):
                return str(message.get("content") or "")
        return ""

    def complete(self, model, messages, tools=None, params=None):
        params = dict(params or {})
        composite = self._composite_for_model(model) if int(params.get("_composite_depth", 0) or 0) < 3 else None
        if composite is not None:
            return self._complete_composite(composite, messages, tools, params)
        routed, handled = self._call_with_api_routes("complete", model, messages, tools, params)
        if handled:
            return routed
        provider, model_name = self.resolve_provider(model)
        if provider.__class__.__name__ == "StubProvider":
            raise RuntimeError(self._provider_unconfigured_message(model))
        try:
            return provider.complete(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def stream(self, model, messages, tools=None, params=None):
        params = dict(params or {})
        composite = self._composite_for_model(model) if int(params.get("_composite_depth", 0) or 0) < 3 else None
        if composite is not None:
            response = self._complete_composite(composite, messages, tools, params)
            text = self._response_text(response)
            return iter([{"type": "text_delta", "text": text}, {"finish_reason": response.get("finish_reason", "stop") if isinstance(response, dict) else "stop"}])
        routed, handled = self._call_with_api_routes("stream", model, messages, tools, params)
        if handled:
            return routed
        provider, model_name = self.resolve_provider(model)
        if provider.__class__.__name__ == "StubProvider":
            raise RuntimeError(self._provider_unconfigured_message(model))
        try:
            return provider.stream(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def supports_stream(self, model):
        provider, _ = self.resolve_provider(model)
        try:
            from domain.ai_client.base_provider import BaseProvider

            return provider.__class__.stream is not BaseProvider.stream
        except Exception:
            return callable(getattr(provider, "stream", None))

    def list_models(self, provider=None):
        """登録済みプロバイダーの既知モデル一覧を返す。"""
        active_provider_ids = self._active_provider_ids()
        if provider is not None and provider not in active_provider_ids:
            return []

        models = get_all_known_models(
            provider_id=provider,
            active_provider_ids=active_provider_ids,
        )
        models = [
            model
            for model in models
            if model.get("provider_id") in active_provider_ids
        ]

        catalog_map = get_provider_catalog_map(active_provider_ids=active_provider_ids)
        seen = {model.get("qualified_model_id") for model in models}
        provider_ids = [provider] if provider else sorted(active_provider_ids)
        for provider_id in provider_ids:
            provider_entry = catalog_map.get(provider_id)
            if provider_entry is None:
                continue
            for raw in self._provider_model_candidates(provider_id):
                candidate = self._normalize_runtime_model(provider_id, provider_entry, raw)
                if candidate is None:
                    continue
                qualified_model_id = candidate.get("qualified_model_id")
                if qualified_model_id in seen:
                    continue
                seen.add(qualified_model_id)
                models.append(candidate)
        return models

    def list_providers(self):
        active_provider_ids = self._active_provider_ids()
        catalog = get_provider_catalog(active_provider_ids=active_provider_ids)
        active = [
            provider
            for provider in catalog
            if provider.get("provider_id") in active_provider_ids
        ]
        known_ids = {provider.get("provider_id") for provider in active}
        for provider_id in sorted(active_provider_ids - known_ids):
            provider = self._providers.get(provider_id)
            active.append(
                {
                    "id": provider_id,
                    "provider_id": provider_id,
                    "name": getattr(provider, "display_name", provider_id.capitalize()),
                    "display_name": getattr(provider, "display_name", provider_id.capitalize()),
                    "kind": "custom",
                    "description": "",
                    "env_vars": [],
                    "base_url_envs": [],
                    "default_model": "",
                    "capabilities": [],
                    "availability": {
                        "active": True,
                        "available": True,
                        "configured": True,
                        "catalog_only": False,
                        "supports_invoke": callable(getattr(provider, "complete", None)),
                        "status": "active",
                    },
                    "metadata": {
                        "catalog_only": False,
                        "supports_invoke": callable(getattr(provider, "complete", None)),
                        "default_base_url": "",
                    },
                }
            )
        return active

    def list_profiles(self, provider=None):
        active_provider_ids = self._active_provider_ids()
        profiles = build_profile_catalog(
            active_provider_ids=active_provider_ids,
            custom_profiles=self._profiles,
        )
        try:
            from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

            service = ModelRuntimeSettingsService()
            profiles.extend(service.runtime_defined_profiles(service.get_settings()))
            profiles.extend(self._api_key_bound_profiles())
        except Exception:
            pass
        profiles = [
            profile
            for profile in profiles
            if (
                not profile.get("provider_id")
                or profile.get("provider_id") in active_provider_ids
                or profile.get("provider_id") == "composite"
                or (isinstance(profile.get("metadata"), dict) and profile["metadata"].get("api_bound"))
            )
        ]
        if provider is not None:
            profiles = [profile for profile in profiles if profile.get("provider_id") == provider]
        return profiles

    def _api_key_bound_profiles(self):
        profiles = []
        for api_key in provider_named_api_keys():
            provider_id = str(api_key.get("provider_id") or "").strip()
            api_id = str(api_key.get("api_id") or "").strip()
            allowed = [str(item).strip() for item in api_key.get("allowed_models", []) if str(item or "").strip()]
            default_model = str(api_key.get("default_model") or "").strip()
            if default_model and default_model not in allowed:
                allowed.insert(0, default_model)
            configured = bool(api_key.get("configured") and read_provider_api_key(provider_id, api_id))
            availability = {
                "configured": configured,
                "active": configured,
                "status": "configured" if configured else "missing_api_key",
                "api_bound": True,
            }
            for model_id in allowed:
                display = f"{model_id} ({api_key.get('name') or api_id})"
                profile_id = f"{provider_id}/{api_id}/{model_id}"
                profiles.append(
                    {
                        "id": profile_id,
                        "profile_id": profile_id,
                        "qualified_model_id": profile_id,
                        "provider_id": provider_id,
                        "provider": provider_id,
                        "model_id": model_id,
                        "model": model_id,
                        "display_name": display,
                        "name": display,
                        "type": "chat",
                        "configured": configured,
                        "availability": dict(availability),
                        "metadata": {
                            "api_bound": True,
                            "api_id": api_id,
                            "base_url": api_key.get("base_url", ""),
                            "notes": api_key.get("notes", ""),
                            "quota_label": api_key.get("quota_label", ""),
                        },
                    }
                )
        return profiles

    def embed(self, model, input_text):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.embed(model_name, input_text)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def image_gen(self, model, prompt, params=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.image_gen(model_name, prompt, params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def image_analyze(self, model, image, prompt):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.image_analyze(model_name, image, prompt)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def transcribe(self, model, audio, params=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.transcribe(model_name, audio, params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def tts(self, model, text, voice=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.tts(model_name, text, voice)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None
