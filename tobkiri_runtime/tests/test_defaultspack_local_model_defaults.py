from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_defaultspack_uses_stub_default_without_cloud_key(tmp_path):
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
    from domain.chat.store import DEFAULT_CHAT_MODEL
    from domain.frontend.registry import FrontendRegistry

    service = ModelRuntimeSettingsService(tmp_path)
    registry = FrontendRegistry(tmp_path)

    assert service.get_preferred_model() == "stub/default"
    assert DEFAULT_CHAT_MODEL == "stub/default"
    assert registry._default_settings()["models"]["model_api_routes"] == ""
    assert "model_api_routes" not in registry._default_settings()["apis"]
