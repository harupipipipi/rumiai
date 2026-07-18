from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_isolated_frontend_settings_selects_cerebras_without_persisting_credential(tmp_path, monkeypatch):
    """All model-selection consumers use the debug run's secret-free settings."""
    settings_path = tmp_path / "isolated" / "frontend_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"models": {"preferred_model": "cerebras/gemma-4-31b"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", str(settings_path))

    from domain.ai_client.client import AIClient
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
    from domain.frontend_settings_store import (
        defaultspack_frontend_settings_path,
    )

    service = ModelRuntimeSettingsService(DEFAULTSPACK_ROOT)
    assert service._settings_path == settings_path.resolve()
    assert service.get_preferred_model() == "cerebras/gemma-4-31b"
    assert (
        defaultspack_frontend_settings_path(DEFAULTSPACK_ROOT)
        == settings_path.resolve()
    )

    AIClient._instance = None
    client = AIClient()
    assert client._settings_path() == settings_path.resolve()
    assert client._settings_data()["models"]["preferred_model"] == "cerebras/gemma-4-31b"
    AIClient._instance = None

    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored == {"models": {"preferred_model": "cerebras/gemma-4-31b"}}
