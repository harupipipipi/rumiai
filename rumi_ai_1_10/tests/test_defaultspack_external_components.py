from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402
from domain.external.audience_policy_registry import AudiencePolicyRegistry  # noqa: E402
from domain.external.input_profile_registry import InputProfileRegistry  # noqa: E402
from domain.external.output_profile_registry import OutputProfileRegistry  # noqa: E402


def test_external_profiles_and_policies_are_component_discoverable():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    assert registry.get("input_profiles", "line.default").id == "line_default"
    assert registry.get("input_profiles", "generic.webhook.default").id == "generic_webhook_default"
    assert registry.get("output_profiles", "discord.bot_channel").id == "discord_bot_channel"
    assert registry.get("audience_policies", "line.production").id == "line_production"


def test_external_registry_apis_preserve_legacy_profile_behavior():
    input_profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("line.default")
    output_profile = OutputProfileRegistry(DEFAULTSPACK_ROOT).get("discord.bot_channel")

    assert input_profile is not None
    assert input_profile.provider == "line"
    assert input_profile.spec["metadata"]["line"]["reply_token"] == "$.replyToken"
    assert output_profile is not None
    assert output_profile.transport == "discord_bot"
    assert output_profile.spec["safety"]["allowed_mentions"]["parse"] == []


def test_audience_policy_registry_preserves_manifest_backed_defaults():
    line_policy = AudiencePolicyRegistry(pack_root=DEFAULTSPACK_ROOT).resolve("line.production")
    discord_policy = AudiencePolicyRegistry(pack_root=DEFAULTSPACK_ROOT).resolve("discord.production")

    assert line_policy["default"] == "deny"
    assert line_policy["require"] == {"verified": True, "message_types": ["text"]}
    assert line_policy["allow_saved_sources"] is True
    assert discord_policy["default"] == "allow"
    assert discord_policy["require"] == {"verified": True}


def test_invalid_external_component_manifest_fails_soft(tmp_path):
    pack_root = tmp_path / "pack"
    bad_component = pack_root / "domain" / "input_profiles" / "bad"
    bad_component.mkdir(parents=True)
    (pack_root / "ecosystem.json").write_text('{"pack_id": "tmp"}', encoding="utf-8")
    (bad_component / "manifest.json").write_text('{"id": "bad"}', encoding="utf-8")

    registry = DomainComponentRegistry(build_domain_component_roots(pack_root))

    assert registry.get("input_profiles", "bad") is None
    assert registry.issues
    assert InputProfileRegistry(pack_root).list_profiles() == []
