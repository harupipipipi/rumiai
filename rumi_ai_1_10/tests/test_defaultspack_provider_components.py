from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
MODEL_CATALOG_ROOT = ROOT / "ecosystem" / "rumi_model_catalog_pack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map  # noqa: E402
from domain.ai_client.providers.component_metadata import (  # noqa: E402
    model_manifests_from_provider_components,
    provider_component_metadata_map,
)
from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402


OPENGATEWAY_MODELS = {
    "gitlawb-opengateway/mimo-v2.5-pro",
    "gitlawb-opengateway/mimo-v2-flash",
    "gitlawb-opengateway/mimo-v2-omni",
    "gitlawb-opengateway/mimo-v2-pro",
    "gitlawb-opengateway/mimo-v2.5",
}


def test_provider_components_include_gitlawb_and_common_provider_aliases():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    assert registry.get("providers", "gitlawb-opengateway").id == "gitlawb-opengateway"
    assert registry.get("providers", "gemini").id == "google"
    assert registry.get("providers", "openrouter").id == "openrouter"
    assert registry.get("providers", "groq").id == "groq"
    assert registry.get("providers", "deepseek").id == "deepseek"


def test_gitlawb_provider_component_preserves_no_key_allowlist_metadata():
    metadata = provider_component_metadata_map()["gitlawb-opengateway"]
    models = model_manifests_from_provider_components("gitlawb-opengateway")
    model_ids = {model["id"] for model in models}
    omni = next(model for model in models if model["id"].endswith("mimo-v2-omni"))

    assert metadata["default_base_url"] == "https://opengateway.gitlawb.com/v1"
    assert metadata["env_vars"] == []
    assert metadata["base_url_envs"] == ["GITLAWB_OPENGATEWAY_BASE_URL"]
    assert metadata["provider_manifest"]["credential_required"] is False
    assert model_ids == OPENGATEWAY_MODELS
    assert omni["metadata"]["vision_verified"] is True


def test_provider_catalog_interops_with_model_catalog_pack_manifests():
    catalog = get_provider_catalog_map()
    models = {model["id"]: model for model in get_all_known_models("gitlawb-opengateway")}

    assert catalog["gitlawb-opengateway"]["metadata"]["default_base_url"] == "https://opengateway.gitlawb.com/v1"
    assert set(models) == OPENGATEWAY_MODELS
    assert models["gitlawb-opengateway/mimo-v2-omni"]["metadata"]["vision_verified"] is True

    provider_manifest_path = MODEL_CATALOG_ROOT / "extensions" / "llm" / "providers" / "gitlawb-opengateway" / "manifest.json"
    provider_manifest = json.loads(provider_manifest_path.read_text(encoding="utf-8"))
    assert provider_manifest["id"] == "gitlawb-opengateway"
    assert provider_manifest["credential_required"] is False

    model_manifest_ids = {
        json.loads(path.read_text(encoding="utf-8"))["id"]
        for path in (provider_manifest_path.parent / "models").glob("*.json")
    }
    assert model_manifest_ids == OPENGATEWAY_MODELS
