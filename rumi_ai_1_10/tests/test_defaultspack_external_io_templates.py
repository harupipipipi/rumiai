from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.io_templates import ExternalIOTemplateRegistry  # noqa: E402
from domain.external.output_profile_registry import OutputProfileRegistry  # noqa: E402


def test_builtin_external_io_templates_split_input_and_output():
    catalog = ExternalIOTemplateRegistry(DEFAULTSPACK_ROOT).catalog()
    input_ids = {item["id"] for item in catalog["input"]}
    output_ids = {item["id"] for item in catalog["output"]}

    assert {"line.input.default", "line.input.computer_use", "discord.input.default", "slack.input.default", "custom.input"} <= input_ids
    assert {
        "line.output.default",
        "discord.output.bot_channel",
        "discord.output.webhook",
        "slack.output.default",
        "custom.output",
    } <= output_ids
    assert {item["id"] for item in catalog["builtin_input"]} == {
        "line.input.default",
        "line.input.computer_use",
        "discord.input.default",
        "slack.input.default",
    }
    discord_webhook = next(item for item in catalog["output"] if item["id"] == "discord.output.webhook")
    assert discord_webhook["setup_mode"] == "copy_paste_select"
    assert discord_webhook["fields"][0]["id"] == "webhook_url"
    assert discord_webhook["fields"][0]["secret"] is True
    assert discord_webhook["copy_paste_setup"]["output_profile_id"] == "discord.webhook"
    assert discord_webhook["copy_paste_setup"]["fields"][0]["paste"] is True
    line_input = next(item for item in catalog["input"] if item["id"] == "line.input.default")
    assert line_input["copy_paste_setup"]["routes"] == ["/api/integrations/line/webhook"]
    assert line_input["copy_paste_setup"]["public_url"]["provider"] == "cloudflare_quick_tunnel"
    assert line_input["copy_paste_setup"]["public_url"]["route_path"] == "/api/integrations/line/webhook"
    assert line_input["copy_paste_setup"]["tokens"][0]["kind"] == "channel_secret"
    line_computer_use = next(item for item in catalog["input"] if item["id"] == "line.input.computer_use")
    assert line_computer_use["copy_paste_setup"]["input_profile_id"] == "line.computer_use"
    assert line_computer_use["copy_paste_setup"]["fields"][0]["id"] == "line_biz_chat_url"
    custom_input = next(item for item in catalog["input"] if item["id"] == "custom.input")
    assert custom_input["setup_mode"] == "custom"


def test_output_profiles_are_provider_neutral_and_discord_has_two_outputs():
    registry = OutputProfileRegistry(DEFAULTSPACK_ROOT)
    assert registry.default_for_provider("line").id == "line.default"
    assert registry.default_for_provider("slack").id == "slack.default"

    discord_profiles = {profile.id for profile in registry.list_profiles() if profile.provider == "discord"}
    assert {"discord.bot_channel", "discord.webhook"} <= discord_profiles


def test_custom_template_registration_uses_extension_directory(tmp_path):
    pack_root = tmp_path / "defaultspack"
    (pack_root / "external_io_templates").mkdir(parents=True)
    registry = ExternalIOTemplateRegistry(pack_root)

    result = registry.upsert_custom(
        {
            "id": "custom.sms.output",
            "direction": "output",
            "provider": "custom",
            "display_name": "SMS Output",
            "fields": [{"id": "phone_number", "secret": False}],
        }
    )

    assert result["success"] is True
    catalog = registry.catalog()
    assert catalog["custom"][0]["id"] == "custom.sms.output"
    assert str(pack_root / "user_data" / "shared" / "external_io_templates") == catalog["extension_paths"]["templates"]
