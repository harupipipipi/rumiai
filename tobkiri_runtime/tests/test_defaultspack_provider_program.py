from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_required_provider_program_has_one_canonical_registry_owner():
    from domain.ai_client.provider_program import provider_program_manifests
    from domain.ai_client.providers import validate_provider_program_coverage

    manifests = provider_program_manifests()

    assert len(manifests) == 79
    assert validate_provider_program_coverage() == []
    assert all(manifest["models"] == [] for manifest in manifests.values())


def test_local_openai_runtimes_discover_served_models_without_credentials(monkeypatch):
    from unittest.mock import patch

    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    monkeypatch.setenv("RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS", "1")
    AIClient._instance = None
    with patch.object(
        OpenAICompatibleProvider,
        "_fetch_remote_models",
        return_value=[
            {
                "id": "vllm/served-model",
                "model_id": "served-model",
                "provider_id": "vllm",
                "type": "chat",
                "metadata": {"source": "remote_models_endpoint"},
            }
        ],
    ), patch.object(OpenAICompatibleProvider, "_load_remote_model_cache", return_value=None):
        client = AIClient()
        models = client.list_models(provider="vllm")

    assert "vllm/served-model" in {model["qualified_model_id"] for model in models}
