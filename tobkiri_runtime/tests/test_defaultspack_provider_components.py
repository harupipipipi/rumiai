from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
MODEL_CATALOG_ROOT = ROOT / "ecosystem" / "rumi_model_catalog_pack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client.providers import (  # noqa: E402
    detect_available_providers,
    get_all_known_models,
    get_provider_catalog_map,
)
from domain.ai_client.providers.component_metadata import (  # noqa: E402
    provider_component_metadata_map,
    provider_manifests_from_components,
)
from domain.components.registry import (  # noqa: E402
    get_domain_component_registry,
)


OPENGATEWAY_MODELS = {
    "gitlawb-opengateway/mimo-v2.5-pro",
    "gitlawb-opengateway/mimo-v2-flash",
    "gitlawb-opengateway/mimo-v2-omni",
    "gitlawb-opengateway/mimo-v2-pro",
    "gitlawb-opengateway/mimo-v2.5",
}


def test_provider_components_include_gitlawb_and_common_provider_aliases():
    from domain.ai_client.provider_identity import canonical_provider_id
    from domain.ai_client.providers import _provider_manifest_map

    descriptors = _provider_manifest_map()
    assert {"gitlawb-opengateway", "google", "openrouter", "groq", "deepseek"} <= set(
        descriptors
    )
    assert canonical_provider_id("gemini") == "google"


def test_gitlawb_catalog_descriptor_preserves_connection_metadata():
    from domain.ai_client.providers import _provider_manifest_map

    descriptor = _provider_manifest_map()["gitlawb-opengateway"]

    assert descriptor["default_base_url"] == "https://opengateway.gitlawb.com/v1"
    assert descriptor["api_key_env"] == "GITLAWB_OPENGATEWAY_API_KEY"
    assert descriptor["base_url_env"] == "GITLAWB_OPENGATEWAY_BASE_URL"
    assert descriptor["credential_required"] is True


def test_provider_catalog_interops_with_model_catalog_pack_manifests():
    catalog = get_provider_catalog_map()

    assert catalog["gitlawb-opengateway"]["metadata"]["default_base_url"] == "https://opengateway.gitlawb.com/v1"
    assert get_all_known_models("gitlawb-opengateway") == []

    provider_manifest_path = MODEL_CATALOG_ROOT / "catalog" / "providers" / "gitlawb-opengateway" / "manifest.json"
    provider_manifest = json.loads(provider_manifest_path.read_text(encoding="utf-8"))
    assert provider_manifest["provider_manifest"]["id"] == "gitlawb-opengateway"
    assert provider_manifest["provider_manifest"]["credential_required"] is True


def test_xiaomi_mimo_provider_components_expose_token_subscription_plan():
    catalog = get_provider_catalog_map()

    catalog_plan = catalog["xiaomi-mimo-global"]["subscription_plans"][0]

    assert catalog_plan["id"] == "mimo_orbit_100t_grant_if_available"
    assert catalog_plan["requires_manual_signup"] is True
    assert catalog_plan["do_not_auto_enable"] is True
    assert get_all_known_models("xiaomi-mimo-global") == []


def test_untrusted_provider_component_manifest_is_not_promoted_or_imported(tmp_path, monkeypatch):
    extra_domain_root = tmp_path / "evil_pack" / "domain"
    provider_root = extra_domain_root / "providers" / "evil_validation"
    provider_root.mkdir(parents=True)
    (tmp_path / "evil_provider.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(tmp_path / 'sentinel.txt')!r}).write_text('imported', encoding='utf-8')\n"
        "class EvilProvider:\n"
        "    def __init__(self):\n"
        "        Path(__file__).with_name('sentinel.txt').write_text('instantiated', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (provider_root / "manifest.json").write_text(
        json.dumps(
            {
                "id": "evil_validation",
                "provider_id": "evil_validation",
                "category": "providers",
                "kind": "llm_provider",
                "version": "1",
                "status": "stable",
                "provider_metadata": {"display_name": "Evil", "kind": "cloud"},
                "provider_manifest": {
                    "id": "evil_validation",
                    "category": "llm_provider",
                    "version": "1",
                    "enabled": True,
                    "credential_required": False,
                    "default_base_url": "https://example.invalid/v1",
                    "entrypoint": "evil_provider:EvilProvider",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_DOMAIN_COMPONENT_ROOTS", str(extra_domain_root))
    try:
        get_domain_component_registry(force_reload=True)

        metadata = provider_component_metadata_map()["evil_validation"]
        manifests = provider_manifests_from_components()
        available = detect_available_providers()

        assert metadata["provider_manifest"] == {}
        assert "evil_validation" not in manifests
        assert "evil_validation" not in available
        assert not (tmp_path / "sentinel.txt").exists()
    finally:
        monkeypatch.delenv("RUMI_DEFAULTSPACK_DOMAIN_COMPONENT_ROOTS", raising=False)
        get_domain_component_registry(force_reload=True)
