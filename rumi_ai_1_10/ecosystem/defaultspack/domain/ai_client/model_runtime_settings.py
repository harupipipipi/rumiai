from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from domain.ai_client.api_key_store import (
    provider_has_api_key,
    set_provider_api_key,
)
from domain.ai_client.model_groups import default_model_groups, normalize_model_groups
from domain.ai_client.model_roles import (
    normalize_utility_model_policy,
    normalize_utility_models,
)


VALID_THINKING_LEVELS = {"none", "low", "medium", "high", "xhigh"}
DEFAULT_MODEL = "stub/default"
LEGACY_CLOUD_DEFAULT_MODEL = "openrouter/tencent/hy3-preview:free"
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

    def get_preferred_model_group(self) -> str:
        return str(self.get_settings().get("preferred_model_group") or "default")

    def set_preferred_model_group(self, group_id: str) -> dict[str, Any]:
        normalized = str(group_id or "").strip() or "default"
        settings = self.update_settings({"preferred_model_group": normalized})
        return {"group_id": settings["preferred_model_group"], "settings": settings}

    def set_auto_route_within_group(self, enabled: bool) -> dict[str, Any]:
        settings = self.update_settings({"auto_route_within_group": bool(enabled)})
        return {"enabled": bool(settings["auto_route_within_group"]), "settings": settings}

    def set_model_role(self, role_id: str, model_id: str) -> dict[str, Any]:
        role = str(role_id or "").strip()
        model = str(model_id or "").strip()
        if not role:
            raise ValueError("role_id is required")
        settings = self.get_settings()
        utility_models = normalize_utility_models(settings.get("utility_models"))
        utility_models[role] = model
        updated = self.update_settings({"utility_models": utility_models})
        return {"role_id": role, "model_id": updated["utility_models"].get(role, ""), "settings": updated}

    def resolve_model_candidates(self, query: str, limit: int = 8) -> dict[str, Any]:
        cleaned_query = str(query or "").strip()
        try:
            max_items = max(0, int(limit))
        except (TypeError, ValueError):
            max_items = 8
        if not cleaned_query:
            return {"query": cleaned_query, "exact": None, "candidates": []}

        settings = self.get_settings()
        favorites = {
            str(item or "").strip()
            for item in settings.get("favorite_profiles", [])
            if str(item or "").strip()
        }
        scored: list[dict[str, Any]] = []
        seen: set[str] = set()
        for profile in self._list_profile_catalog():
            if not self._is_chat_profile(profile):
                continue
            candidate = self._candidate_from_profile(profile, favorites)
            candidate_key = str(candidate.get("profile_id") or candidate.get("qualified_model_id") or "").strip()
            if not candidate_key or candidate_key in seen:
                continue
            match_kind, base_score = self._candidate_match(candidate, cleaned_query)
            if base_score <= 0:
                continue
            candidate["score"] = self._candidate_score(candidate, base_score)
            candidate["_match_kind"] = match_kind
            seen.add(candidate_key)
            scored.append(candidate)

        scored.sort(
            key=lambda item: (
                -int(item.get("score") or 0),
                str(item.get("label") or item.get("display_name") or item.get("profile_id") or "").casefold(),
                str(item.get("profile_id") or "").casefold(),
            )
        )
        exact_id_candidates = [item for item in scored if item.get("_match_kind") == "exact_id"]
        exact_field_candidates = [item for item in scored if item.get("_match_kind") == "exact_field"]
        if len(exact_id_candidates) == 1:
            exact = self._public_candidate(exact_id_candidates[0])
        elif len(exact_id_candidates) == 0 and len(exact_field_candidates) == 1:
            exact = self._public_candidate(exact_field_candidates[0])
        else:
            exact = None
        return {
            "query": cleaned_query,
            "exact": exact,
            "candidates": [self._public_candidate(item) for item in scored[:max_items]],
        }

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
            "preferred_model_group": "default",
            "auto_route_within_group": True,
            "model_groups": default_model_groups(),
            "on_switch_to_non_vision_with_images": "auto_bridge",
            "thinking_level": DEFAULT_THINKING_LEVEL,
            "favorite_profiles": [DEFAULT_MODEL],
            "thinking_level_by_profile": {DEFAULT_MODEL: DEFAULT_THINKING_LEVEL},
            "thinking_level_by_conversation": {},
            "utility_models": normalize_utility_models({}),
            "utility_model_policy": normalize_utility_model_policy({}),
            "model_api_routes": "",
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
        sanitized["model_api_routes"] = self._normalize_model_api_routes(
            sanitized.get("model_api_routes", "")
        )
        if "model_groups" in sanitized:
            sanitized["model_groups"] = normalize_model_groups(sanitized.get("model_groups"))
        if "utility_models" in sanitized:
            sanitized["utility_models"] = normalize_utility_models(sanitized.get("utility_models"))
        if "utility_model_policy" in sanitized:
            sanitized["utility_model_policy"] = normalize_utility_model_policy(sanitized.get("utility_model_policy"))
        if "preferred_model_group" in sanitized:
            sanitized["preferred_model_group"] = str(sanitized.get("preferred_model_group") or "default").strip() or "default"
        if "auto_route_within_group" in sanitized:
            sanitized["auto_route_within_group"] = bool(sanitized.get("auto_route_within_group"))
        if "on_switch_to_non_vision_with_images" in sanitized:
            policy = str(sanitized.get("on_switch_to_non_vision_with_images") or "auto_bridge").strip()
            sanitized["on_switch_to_non_vision_with_images"] = policy if policy in {"auto_bridge", "ask", "block", "ignore"} else "auto_bridge"
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
        if preferred_model == LEGACY_CLOUD_DEFAULT_MODEL and not provider_has_api_key(
            "openrouter",
            pack_root=self._pack_root,
        ):
            preferred_model = DEFAULT_MODEL
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
        models["model_api_routes"] = self._normalize_model_api_routes(models.get("model_api_routes", ""))
        models["preferred_model_group"] = str(models.get("preferred_model_group") or "default").strip() or "default"
        models["auto_route_within_group"] = bool(models.get("auto_route_within_group", True))
        models["model_groups"] = normalize_model_groups(models.get("model_groups"))
        models["utility_models"] = normalize_utility_models(models.get("utility_models"))
        models["utility_model_policy"] = normalize_utility_model_policy(models.get("utility_model_policy"))
        switch_policy = str(models.get("on_switch_to_non_vision_with_images") or "auto_bridge").strip()
        models["on_switch_to_non_vision_with_images"] = switch_policy if switch_policy in {"auto_bridge", "ask", "block", "ignore"} else "auto_bridge"
        return models

    @staticmethod
    def _normalize_model_api_routes(value: Any) -> str:
        if isinstance(value, list):
            lines = [str(item).strip() for item in value if str(item).strip()]
        else:
            lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
        return "\n".join(lines) + ("\n" if lines else "")

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

    def _list_profile_catalog(self) -> list[dict[str, Any]]:
        try:
            from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
        except ModuleNotFoundError:
            try:
                from backend.ai_client.provider_catalog import list_profile_catalog
            except ModuleNotFoundError:
                list_profile_catalog = None

        if list_profile_catalog is not None:
            try:
                profiles = list_profile_catalog()
                if isinstance(profiles, list) and profiles:
                    return [profile for profile in profiles if isinstance(profile, dict)]
            except Exception:
                pass
        return [self._fallback_stub_profile()]

    @staticmethod
    def _fallback_stub_profile() -> dict[str, Any]:
        return {
            "id": DEFAULT_MODEL,
            "profile_id": DEFAULT_MODEL,
            "qualified_model_id": DEFAULT_MODEL,
            "provider_id": "stub",
            "provider": "stub",
            "provider_display_name": "Stub",
            "model_id": "default",
            "model": "default",
            "display_name": "Stub Default",
            "name": "Stub Default",
            "availability": {
                "active": True,
                "configured": True,
                "local": True,
                "status": "configured",
            },
        }

    @staticmethod
    def _is_chat_profile(profile: dict[str, Any]) -> bool:
        model_type = str(profile.get("type") or "chat").strip().lower()
        return not model_type or model_type == "chat"

    def _candidate_from_profile(self, profile: dict[str, Any], favorites: set[str]) -> dict[str, Any]:
        profile_id = str(profile.get("profile_id") or profile.get("id") or profile.get("qualified_model_id") or "").strip()
        qualified_model_id = str(profile.get("qualified_model_id") or profile_id).strip()
        provider_id = str(profile.get("provider_id") or profile.get("provider") or "").strip()
        model_id = str(profile.get("model_id") or profile.get("model") or "").strip()
        if not provider_id and qualified_model_id and "/" in qualified_model_id:
            provider_id, model_id_from_qualified = qualified_model_id.split("/", 1)
            model_id = model_id or model_id_from_qualified
        if not model_id and qualified_model_id and "/" in qualified_model_id:
            _provider_id, model_id = qualified_model_id.split("/", 1)
        if not qualified_model_id and provider_id and model_id:
            qualified_model_id = f"{provider_id}/{model_id}"
        if not profile_id:
            profile_id = qualified_model_id

        availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
        provider_display_name = str(
            profile.get("provider_display_name")
            or profile.get("provider_name")
            or provider_id
            or ""
        ).strip()
        display_name = str(
            profile.get("display_name")
            or profile.get("name")
            or profile.get("disambiguated_name")
            or model_id
            or profile_id
        ).strip()
        label = f"{provider_display_name} / {display_name}" if provider_display_name else display_name
        local = bool(
            profile.get("local")
            or availability.get("local")
            or availability.get("offline")
            or provider_id in {"stub", "ollama", "lmstudio", "vllm"}
        )
        configured = bool(
            profile.get("configured")
            or availability.get("configured")
            or availability.get("active")
            or str(availability.get("status", "")).lower() in {"configured", "active"}
            or provider_id == "stub"
        )
        requires_api_key = bool(provider_id and provider_id not in {"stub", "rumi"} and not local and not configured)
        favorite = any(
            item in favorites
            for item in {
                profile_id,
                qualified_model_id,
                model_id,
                f"{provider_id}/{model_id}" if provider_id and model_id else "",
            }
            if item
        )

        return {
            "profile_id": profile_id,
            "qualified_model_id": qualified_model_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "display_name": display_name,
            "provider_display_name": provider_display_name,
            "configured": configured,
            "local": local,
            "requires_api_key": requires_api_key,
            "api_key_required": requires_api_key,
            "api_key_configured": configured,
            "availability": deepcopy(availability),
            "type": str(profile.get("type") or "chat"),
            "favorite": favorite,
            "label": label,
            "disambiguated_name": str(profile.get("disambiguated_name") or "").strip(),
            "score": 0,
        }

    def _candidate_match(self, candidate: dict[str, Any], query: str) -> tuple[str, int]:
        normalized_query = self._normalize_search_key(query)
        if not normalized_query:
            return "", 0

        provider_id = str(candidate.get("provider_id") or "").strip()
        model_id = str(candidate.get("model_id") or "").strip()
        provider_display_name = str(candidate.get("provider_display_name") or "").strip()
        provider_model_id = f"{provider_id}/{model_id}" if provider_id and model_id else ""
        provider_display_model_id = f"{provider_display_name}/{model_id}" if provider_display_name and model_id else ""

        exact_id_fields = {
            str(candidate.get("profile_id") or ""),
            str(candidate.get("qualified_model_id") or ""),
        }
        exact_fields = {
            str(candidate.get("display_name") or ""),
            str(candidate.get("model_id") or ""),
            provider_model_id,
            provider_display_model_id,
            str(candidate.get("label") or ""),
            str(candidate.get("disambiguated_name") or ""),
        }
        search_fields = exact_id_fields | exact_fields | {
            provider_id,
            provider_display_name,
        }
        normalized_exact_ids = {self._normalize_search_key(item) for item in exact_id_fields if item}
        normalized_exact_fields = {self._normalize_search_key(item) for item in exact_fields if item}
        normalized_search_fields = {
            self._normalize_search_key(item)
            for item in search_fields
            if item and self._normalize_search_key(item)
        }

        if normalized_query in normalized_exact_ids:
            return "exact_id", 1000
        if normalized_query in normalized_exact_fields:
            return "exact_field", 950
        if any(item.startswith(normalized_query) for item in normalized_search_fields):
            return "prefix", 700
        if any(normalized_query in item for item in normalized_search_fields):
            return "substring", 500
        return "", 0

    @staticmethod
    def _candidate_score(candidate: dict[str, Any], base_score: int) -> int:
        return (
            base_score
            + (24 if candidate.get("configured") else 0)
            + (12 if candidate.get("local") else 0)
            + (6 if candidate.get("favorite") else 0)
        )

    @staticmethod
    def _normalize_search_key(value: Any) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    @staticmethod
    def _public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in candidate.items()
            if not str(key).startswith("_")
        }

    def _deep_merge(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
