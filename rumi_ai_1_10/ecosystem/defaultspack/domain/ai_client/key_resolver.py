from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .api_key_store import _get_store, _secrets_dir, provider_secret_keys
from .key_manager import KeyManager


class KeyResolver:
    """Resolve the best named API key for a model/provider/profile/agent context."""

    def __init__(self, root: Path | None = None, *, pack_root: Path | None = None) -> None:
        self.manager = KeyManager(root, pack_root=pack_root)

    def resolve(self, context: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(context.get("provider_id") or self._provider_from_model(context.get("model"))).lower()
        preferred = str(context.get("preferred_key_id") or context.get("api_key_id") or "")
        candidates = self.manager.list_keys()
        for key_id in [preferred, str(context.get("agent_default_key_id") or ""), str(context.get("profile_default_key_id") or ""), str(context.get("provider_default_key_id") or "")]:
            if not key_id:
                continue
            candidate = next((item for item in candidates if item.get("key_id") == key_id), None)
            if candidate and self._matches(candidate, context, provider_id):
                source = "preferred_key_id" if key_id == preferred else "named_default"
                return {"source": source, "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        agent_id = str(context.get("agent_id") or "")
        if agent_id:
            for candidate in candidates:
                if agent_id in set(candidate.get("allowed_agents") or candidate.get("agent_ids") or []):
                    if self._matches(candidate, context, provider_id):
                        return {"source": "agent_default", "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        profile_id = str(context.get("profile_id") or "")
        if profile_id:
            for candidate in candidates:
                if profile_id in set(candidate.get("allowed_profiles") or candidate.get("profile_ids") or []):
                    if self._matches(candidate, context, provider_id):
                        return {"source": "profile_default", "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        if provider_id:
            for candidate in candidates:
                if candidate.get("default_for_provider") and candidate.get("provider_id") == provider_id:
                    if self._matches(candidate, context, provider_id):
                        return {"source": "provider_default", "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        for key_id in [str(item) for item in context.get("fallback_key_ids") or [] if str(item)]:
            candidate = next((item for item in candidates if item.get("key_id") == key_id), None)
            if candidate and self._matches(candidate, context, provider_id):
                return {"source": "fallback_key", "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        for candidate in candidates:
            if self._matches(candidate, context, provider_id):
                return {"source": "named", "key": candidate, "api_key_id": candidate["key_id"], "secret_name": candidate.get("secret_name")}
        for secret_key in provider_secret_keys(provider_id):
            if os.environ.get(secret_key, "").strip():
                return {"source": "legacy_env", "provider_id": provider_id, "secret_name": secret_key, "api_key_id": None}
        for secret_key in provider_secret_keys(provider_id):
            if (_secrets_dir(self.manager.pack_root) / f"{secret_key}.json").exists():
                return {"source": "legacy_secret", "provider_id": provider_id, "secret_name": secret_key, "api_key_id": None}
        return {"source": "missing", "provider_id": provider_id, "api_key_id": None}

    def resolve_api_key(
        self,
        *,
        provider_id: str = "",
        profile_id: str = "",
        agent_id: str = "",
        preferred_key_id: str = "",
        model: str = "",
        fallback: str | list[str] = "",
        fallback_key_ids: list[str] | None = None,
        record_usage: bool = False,
    ) -> dict[str, Any]:
        fallbacks = list(fallback_key_ids or [])
        fallback_value = fallback if isinstance(fallback, str) else ""
        if isinstance(fallback, list):
            fallbacks.extend(str(item) for item in fallback)
        resolved = self.resolve(
            {
                "provider_id": provider_id,
                "profile_id": profile_id,
                "agent_id": agent_id,
                "preferred_key_id": preferred_key_id,
                "model": model,
                "fallback_key_ids": fallbacks,
            }
        )
        value = self.read_api_key(resolved)
        if not value and fallback_value:
            value = fallback_value
            resolved = {**resolved, "source": "fallback"}
        key = resolved.get("key") if isinstance(resolved.get("key"), dict) else {}
        result = {
            **resolved,
            "provider_id": provider_id or resolved.get("provider_id"),
            "configured": bool(value),
            "value": value or "",
            "env_key": key.get("env_var") or resolved.get("secret_name") or "",
        }
        if record_usage and result.get("api_key_id"):
            try:
                from .key_usage import KeyUsageTracker

                KeyUsageTracker().record(str(result["api_key_id"]), requests=1)
            except Exception:
                pass
        return result

    def redacted_resolution(self, resolved: dict[str, Any]) -> dict[str, Any]:
        return {
            key: ("[redacted]" if key in {"value", "api_key", "secret"} and value else value)
            for key, value in resolved.items()
            if key != "key" or not isinstance(value, dict)
        }

    def read_api_key(self, resolved: dict[str, Any]) -> str | None:
        if resolved.get("api_key_id"):
            return self.manager.read_secret(str(resolved["api_key_id"]))
        if resolved.get("source") == "legacy_env" and resolved.get("secret_name"):
            return os.environ.get(str(resolved["secret_name"]))
        if resolved.get("source") == "legacy_secret" and resolved.get("secret_name"):
            return _get_store(self.manager.pack_root)._internal_read_value(
                str(resolved["secret_name"]),
                caller_id="defaultspack.key_resolver",
            )
        return None

    def _matches(self, key: dict[str, Any], context: dict[str, Any], provider_id: str) -> bool:
        if key.get("enabled") is False:
            return False
        if provider_id and key.get("provider_id") != provider_id:
            return False
        checks = [
            ("allowed_profiles", "profile_id"),
            ("allowed_agents", "agent_id"),
            ("allowed_models", "model"),
        ]
        for list_key, context_key in checks:
            allowed = key.get(list_key) or []
            value = context.get(context_key)
            if allowed and value not in allowed:
                return False
        return True

    @staticmethod
    def _provider_from_model(model: Any) -> str:
        text = str(model or "")
        return text.split("/", 1)[0] if "/" in text else text
