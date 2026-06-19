"""blocks.mobile.capabilities — プロバイダー/モデル/プロファイル/テンプレート一括取得。

PCへ接続したスマホがプロバイダーカタログを自動取得するためのエンドポイント。
既存の provider_catalog / template gallery を集約して返す。

入力:
  {
    "include_templates": bool (optional, default true),
    "provider": str (optional — モデルを特定プロバイダーに絞る)
  }

出力:
  {
    "status": "ok",
    "data": {
      "providers": [...],
      "models": [...],
      "profiles": [...],
      "templates": [...]
    }
  }
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
    list_model_catalog,
    list_profile_catalog,
    list_provider_catalog,
)
from ecosystem.defaultspack.domain.template.gallery import get_gallery


def _provider_summary(provider: dict) -> dict:
    """モバイルへ送る最小限のプロバイダー情報。シークレットは含めない。"""
    return {
        "provider_id": str(provider.get("provider_id") or provider.get("id") or ""),
        "display_name": str(provider.get("display_name") or provider.get("provider_metadata", {}).get("display_name") or ""),
        "kind": str(provider.get("kind") or provider.get("category") or ""),
        "configured": bool(provider.get("configured")),
        "openai_compatible": bool(provider.get("openai_compatible")),
        "local": bool(provider.get("local")),
        "catalog_only": bool(provider.get("catalog_only")),
        "default_model": str(provider.get("default_model") or provider.get("provider_metadata", {}).get("default_model") or ""),
        "capabilities": list(provider.get("capabilities") or []),
        "env_vars": list(provider.get("env_vars") or provider.get("provider_metadata", {}).get("env_vars") or []),
        "base_url_envs": list(provider.get("base_url_envs") or provider.get("provider_metadata", {}).get("base_url_envs") or []),
        "configured_api_count": int(provider.get("configured_api_count") or 0),
    }


def _model_summary(model: dict) -> dict:
    return {
        "id": str(model.get("id") or ""),
        "provider_id": str(model.get("provider_id") or ""),
        "model_id": str(model.get("model_id") or ""),
        "display_name": str(model.get("display_name") or ""),
        "type": str(model.get("type") or "chat"),
        "enabled": bool(model.get("enabled")),
        "max_context": int(model.get("max_context") or model.get("max_context_tokens") or -1),
        "supports_thinking": bool(model.get("supports_thinking")),
        "supports_vision": bool(model.get("supports_vision")),
        "supports_tool_calling": bool(model.get("supports_tool_calling")),
        "thinking_levels": list(model.get("thinking_levels") or []),
        "default_thinking_level": model.get("default_thinking_level"),
        "speed_tier": str(model.get("speed_tier") or "balanced"),
        "cost_tier": str(model.get("cost_tier") or "unknown"),
        "capability_tags": list(model.get("capability_tags") or []),
    }


def _profile_summary(profile: dict) -> dict:
    return {
        "profile_id": str(profile.get("profile_id") or profile.get("id") or ""),
        "provider_id": str(profile.get("provider_id") or ""),
        "model_id": str(profile.get("model_id") or ""),
        "display_name": str(profile.get("display_name") or ""),
        "qualified_model_id": str(profile.get("qualified_model_id") or ""),
        "type": str(profile.get("type") or "chat"),
        "max_context": int(profile.get("max_context") or profile.get("max_context_tokens") or -1),
        "supports_thinking": bool(profile.get("supports_thinking")),
        "supports_vision": bool(profile.get("supports_vision")),
        "supports_tool_calling": bool(profile.get("supports_tool_calling")),
    }


def _template_summary(entry: dict) -> dict:
    return {
        "entry_id": str(entry.get("entry_id") or ""),
        "name": str(entry.get("name") or ""),
        "description": str(entry.get("description") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "tags": list(entry.get("tags") or []),
        "updated_at": str(entry.get("updated_at") or ""),
    }


def _merged_input(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        return {}
    merged: dict = {}
    for container_key in ("query_params", "params", "body", "query"):
        value = input_data.get(container_key)
        if isinstance(value, dict):
            merged.update(value)
    for key, value in input_data.items():
        if key in {"query_params", "params", "body", "query"}:
            continue
        merged[key] = value
    return merged


def _optional_bool(value, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def run(input_data, context):
    del context
    args = _merged_input(input_data)

    include_templates = _optional_bool(args.get("include_templates"), True)
    provider_filter = str(args.get("provider") or "")

    providers = [_provider_summary(p) for p in list_provider_catalog()]
    models = [_model_summary(m) for m in list_model_catalog(provider=provider_filter)]
    profiles = [_profile_summary(p) for p in list_profile_catalog()]

    templates: list[dict] = []
    if include_templates:
        try:
            gallery = get_gallery()
            templates = [_template_summary(e) for e in gallery.list_entries()]
        except Exception:
            templates = []

    return ok(
        {
            "providers": providers,
            "models": models,
            "profiles": profiles,
            "templates": templates,
        }
    )
