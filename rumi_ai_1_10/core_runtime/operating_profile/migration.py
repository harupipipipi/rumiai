from __future__ import annotations

from typing import Any, Mapping

from .compiler import compile_operating_profile
from .models import OperatingProfile


def migrate_legacy_operating_profile(raw: Mapping[str, Any] | None) -> OperatingProfile:
    data = dict(raw or {})
    answers = {
        "profile_id": data.get("profile_id") or data.get("id") or "default",
        "preset": data.get("operating_preset") or data.get("preset") or "balanced_local",
        "occupation": data.get("occupation"),
        "actions": data.get("actions") or data.get("permissions") or {},
    }
    return compile_operating_profile(answers)
