from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService  # noqa: E402


def test_model_runtime_settings_preferred_model_and_thinking_level(tmp_path):
    service = ModelRuntimeSettingsService(tmp_path)

    assert service.get_preferred_model() == "stub/default"
    preferred = service.set_preferred_model("stub/default")
    assert preferred["profile_id"] == "stub/default"

    updated = service.set_thinking_level("high")
    assert updated["level"] == "high"
    assert service.get_thinking_level()["level"] == "high"


def test_effective_thinking_level_resolution_order(tmp_path):
    service = ModelRuntimeSettingsService(tmp_path)
    service.set_thinking_level("low", scope="global")
    service.set_thinking_level("medium", scope="profile", profile_id="stub/default")
    service.set_thinking_level("xhigh", scope="conversation", conversation_id="conv-1")

    assert service.get_effective_thinking_level("stub/default", "conv-1")["level"] == "xhigh"
    assert service.get_effective_thinking_level("stub/default", "conv-2")["level"] == "medium"
    assert service.get_effective_thinking_level("other", "conv-2")["level"] == "low"


def test_thinking_level_validation_and_provider_normalization(tmp_path):
    service = ModelRuntimeSettingsService(tmp_path)

    assert service.validate_thinking_level("bogus")["valid"] is False
    normalized = service.normalize_for_provider("openai", "gpt-5", "xhigh")

    assert normalized["provider_params"]["reasoning_effort"] == "high"
    assert normalized["level"] == "high"
