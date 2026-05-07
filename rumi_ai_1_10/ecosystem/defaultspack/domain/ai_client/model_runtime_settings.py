from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from domain.ai_client.api_key_store import (
    provider_has_api_key,
    provider_key_status,
    set_provider_api_key,
)


VALID_THINKING_LEVELS = {"none", "low", "medium", "high", "xhigh"}
DEFAULT_MODEL = "openrouter/tencent/hy3-preview:free"
DEFAULT_THINKING_LEVEL = "medium"


class ModelRuntimeSettingsService:
    """Owns model runtime settings persisted in frontend_settings.json."""

    def __init__(self, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._settings_path = self._pack_root / "user_data" / "shared" / "frontend_settings.json"

    def get_settings(self) -> dict[str, Any]:
        return self.refresh_models_settings(self._read_all().get("models", {}))

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        all_settings = self._read_all()
        current_models = all_settings.get("models", {})
        if not isinstance(current_models, dict):
            current_models = {}
        sanitized = self.sanitize_models_patch(patch or {})
        merged = self._deep_merge(current_models, sanitized)
        all_settings["models"] = self.refresh_models_settings(merged)
        self._write_all(all_settings)
        return all_settings["models"]

    def get_preferred_model(self) -> str:
        return str(self.get_settings().get("preferred_model") or DEFAULT_MODEL)

    def set_preferred_model(self, profile_id: str) -> dict[str, Any]:
        profile = str(profile_id or "").strip()
        if not profile:
            raise ValueError("profile_id is required")
        settings = self.update_settings({"preferred_model": profile})
        return {"profile_id": settings["preferred_model"], "settings": settings}

    def get_thinking_level(
        self,
        scope: str = "global",
        profile_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        settings = self.get_settings()
        scope = str(scope or "global")
        if scope == "profile" and profile_id:
            level = settings.get("thinking_level_by_profile", {}).get(profile_id)
        elif scope == "conversation" and conversation_id:
            level = settings.get("thinking_level_by_conversation", {}).get(conversation_id)
        else:
            level = settings.get("thinking_level")
            scope = "global"
        return {
            "scope": scope,
            "profile_id": profile_id,
            "conversation_id": conversation_id,
            "level": self._normalize_level(level),
        }

    def set_thinking_level(
        self,
        level: str,
        scope: str = "global",
        profile_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validate_thinking_level(level, profile_id)
        if not validation["valid"]:
            raise ValueError(validation["message"])
        normalized = validation["level"]
        scope = str(scope or "global")
        settings = self.get_settings()
        patch: dict[str, Any] = {}
        if scope == "profile":
            if not profile_id:
                raise ValueError("profile_id is required for profile thinking level")
            values = dict(settings.get("thinking_level_by_profile") or {})
            values[str(profile_id)] = normalized
            patch["thinking_level_by_profile"] = values
        elif scope == "conversation":
            if not conversation_id:
                raise ValueError("conversation_id is required for conversation thinking level")
            values = dict(settings.get("thinking_level_by_conversation") or {})
            values[str(conversation_id)] = normalized
            patch["thinking_level_by_conversation"] = values
        elif scope == "turn":
            return {"scope": "turn", "level": normalized, "persisted": False}
        else:
            patch["thinking_level"] = normalized
            scope = "global"
        updated = self.update_settings(patch)
        return {
            "scope": scope,
            "profile_id": profile_id,
            "conversation_id": conversation_id,
            "level": normalized,
            "persisted": scope != "turn",
            "settings": updated,
        }

    def get_effective_thinking_level(
        self,
        profile_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        settings = self.get_settings()
        if conversation_id:
            by_conversation = settings.get("thinking_level_by_conversation", {})
            if isinstance(by_conversation, dict):
                level = by_conversation.get(conversation_id)
                if self._normalize_level(level) == level:
                    return {"level": level, "scope": "conversation", "conversation_id": conversation_id}
        if profile_id:
            by_profile = settings.get("thinking_level_by_profile", {})
            if isinstance(by_profile, dict):
                level = by_profile.get(profile_id)
                if self._normalize_level(level) == level:
                    return {"level": level, "scope": "profile", "profile_id": profile_id}
        return {"level": self._normalize_level(settings.get("thinking_level")), "scope": "global"}

    def validate_thinking_level(self, level: str, profile_id: str | None = None) -> dict[str, Any]:
        del profile_id
        normalized = self._normalize_level(level)
        return {
            "valid": normalized in VALID_THINKING_LEVELS and str(level or "").strip() in VALID_THINKING_LEVELS,
            "level": normalized,
            "message": "" if str(level or "").strip() in VALID_THINKING_LEVELS else "thinking level must be one of none, low, medium, high, xhigh",
        }

    def normalize_for_provider(self, provider_id: str, model_id: str, level: str) -> dict[str, Any]:
        normalized = self._normalize_level(level)
        provider = str(provider_id or "").strip().lower()
        result: dict[str, Any] = {
            "provider_id": provider_id,
            "model_id": model_id,
            "requested_level": level,
            "level": normalized,
        }
        if provider in {"openai", "openai_compatible", "openrouter"}:
            effort = "high" if normalized == "xhigh" else normalized
            if effort != "none":
                result["provider_params"] = {"reasoning_effort": effort}
            else:
                result["provider_params"] = {}
            result["level"] = effort if normalized == "xhigh" and provider == "openai" else normalized
        elif provider == "anthropic":
            result["provider_params"] = {"thinking_level": normalized}
        elif provider == "google":
            result["provider_params"] = {"thinking_level": normalized}
        else:
            result["provider_params"] = {"thinking_level": normalized}
        return result

    def default_model_settings(self) -> dict[str, Any]:
        return {
            "preferred_model": DEFAULT_MODEL,
            "thinking_level": DEFAULT_THINKING_LEVEL,
            "favorite_profiles": [DEFAULT_MODEL, "stub/default"],
            "thinking_level_by_profile": {DEFAULT_MODEL: DEFAULT_THINKING_LEVEL},
            "thinking_level_by_conversation": {},
            "google_api_key": "",
            "google_api_key_configured": provider_has_api_key("google", pack_root=self._pack_root),
            "openrouter_api_key": "",
            "openrouter_api_key_configured": provider_has_api_key("openrouter", pack_root=self._pack_root),
        }

    def sanitize_models_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        sanitized = deepcopy(patch or {})
        for provider_id, field_id, configured_field in (
            ("google", "google_api_key", "google_api_key_configured"),
            ("openrouter", "openrouter_api_key", "openrouter_api_key_configured"),
        ):
            raw_key = sanitized.pop(field_id, None)
            if isinstance(raw_key, str) and raw_key.strip():
                result = set_provider_api_key(provider_id, raw_key, pack_root=self._pack_root)
                sanitized[configured_field] = bool(result.get("success"))
            else:
                sanitized[configured_field] = provider_has_api_key(provider_id, pack_root=self._pack_root)
            sanitized[field_id] = ""
        return sanitized

    def refresh_models_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        models = self._deep_merge(self.default_model_settings(), values if isinstance(values, dict) else {})
        models["google_api_key"] = ""
        models["google_api_key_configured"] = provider_has_api_key("google", pack_root=self._pack_root)
        models["openrouter_api_key"] = ""
        models["openrouter_api_key_configured"] = provider_has_api_key("openrouter", pack_root=self._pack_root)

        favorite_profiles = models.get("favorite_profiles")
        if isinstance(favorite_profiles, str):
            try:
                favorite_profiles = json.loads(favorite_profiles)
            except json.JSONDecodeError:
                favorite_profiles = [line.strip() for line in favorite_profiles.splitlines()]
        if not isinstance(favorite_profiles, list):
            preferred = str(models.get("preferred_model") or DEFAULT_MODEL).strip()
            favorite_profiles = [preferred] if preferred else ["stub/default"]
        normalized_favorites: list[str] = []
        for item in favorite_profiles:
            profile_id = str(item or "").strip()
            if profile_id and profile_id not in normalized_favorites:
                normalized_favorites.append(profile_id)
        preferred_model = str(models.get("preferred_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        if preferred_model not in normalized_favorites:
            normalized_favorites.insert(0, preferred_model)
        models["preferred_model"] = preferred_model
        models["favorite_profiles"] = normalized_favorites or ["stub/default"]

        for key in ("thinking_level_by_profile", "thinking_level_by_conversation"):
            values_by_scope = models.get(key)
            if isinstance(values_by_scope, str):
                try:
                    values_by_scope = json.loads(values_by_scope)
                except json.JSONDecodeError:
                    values_by_scope = {}
            models[key] = values_by_scope if isinstance(values_by_scope, dict) else {}
        models["thinking_level"] = self._normalize_level(models.get("thinking_level"))
        return models

    def _read_all(self) -> dict[str, Any]:
        values: dict[str, Any] = {"models": self.default_model_settings()}
        try:
            saved = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                values = self._deep_merge(values, saved)
        except (OSError, json.JSONDecodeError):
            pass
        values["models"] = self.refresh_models_settings(values.get("models", {}))
        return values

    def _write_all(self, values: dict[str, Any]) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(values, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_level(self, value: Any) -> str:
        level = str(value or "").strip()
        return level if level in VALID_THINKING_LEVELS else DEFAULT_THINKING_LEVEL

    def _deep_merge(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
