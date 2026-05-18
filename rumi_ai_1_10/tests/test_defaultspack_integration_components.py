from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402


def test_integration_components_advertise_legacy_routes_and_imports():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    line = registry.get("integrations", "line")
    discord = registry.get("integrations", "discord")
    slack = registry.get("integrations", "slack")

    assert line is not None
    assert discord is not None
    assert slack is not None
    assert line.manifest["routes"][0]["path"] == "/api/integrations/line/webhook"
    assert {route["path"] for route in discord.manifest["routes"]} == {
        "/api/integrations/discord/interactions",
        "/api/integrations/discord/events",
    }
    assert slack.manifest["routes"][0]["path"] == "/api/integrations/slack/events"


def test_legacy_integration_blocks_alias_component_modules():
    from blocks.integrations import discord as discord_block  # noqa: E402
    from blocks.integrations import line as line_block  # noqa: E402
    from blocks.integrations import slack as slack_block  # noqa: E402
    from domain.integrations.discord import inbound as discord_inbound  # noqa: E402
    from domain.integrations.line import inbound as line_inbound  # noqa: E402
    from domain.integrations.slack import inbound as slack_inbound  # noqa: E402

    assert line_block is line_inbound
    assert discord_block is discord_inbound
    assert slack_block is slack_inbound
    assert line_block.run is line_inbound.run
    assert discord_block.DISCORD_PING == 1
    assert slack_block.run is slack_inbound.run
