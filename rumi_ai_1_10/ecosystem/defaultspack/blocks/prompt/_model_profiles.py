from __future__ import annotations

from typing import Any


def with_model_profiles(input_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(input_data) if isinstance(input_data, dict) else {}
    if isinstance(data.get("model_profiles"), list):
        return data
    try:
        from domain.ai_client.providers import build_profile_catalog

        profiles = build_profile_catalog()
    except Exception:
        profiles = []
    data["model_profiles"] = [profile for profile in profiles if isinstance(profile, dict)]
    return data
