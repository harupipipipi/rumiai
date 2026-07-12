from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402


def test_gateway_and_url_provider_components_are_discoverable():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    assert registry.get("gateway_channels", "line").manifest["entrypoints"]["adapter"] == "adapter.py"
    assert registry.get("gateway_channels", "discord").manifest["entrypoints"]["adapter"] == "adapter.py"
    assert registry.get("gateway_channels", "slack").manifest["entrypoints"]["adapter"] == "adapter.py"
    assert registry.get("webhook_url_providers", "cloudflare_quick_tunnel").manifest["entrypoints"]["provider"] == "provider.py"
    assert registry.get("webhook_url_providers", "static").manifest["entrypoints"]["provider"] == "provider.py"


def test_legacy_gateway_channel_imports_delegate_to_components():
    from domain.gateway.channels.discord import DiscordChannel  # noqa: E402
    from domain.gateway.channels.line import LineChannel  # noqa: E402
    from domain.gateway.channels.slack import SlackChannel  # noqa: E402
    from domain.gateway_channels.discord.adapter import DiscordChannel as ComponentDiscordChannel  # noqa: E402
    from domain.gateway_channels.line.adapter import LineChannel as ComponentLineChannel  # noqa: E402
    from domain.gateway_channels.slack.adapter import SlackChannel as ComponentSlackChannel  # noqa: E402

    assert LineChannel is ComponentLineChannel
    assert DiscordChannel is ComponentDiscordChannel
    assert SlackChannel is ComponentSlackChannel


def test_legacy_url_provider_imports_alias_component_modules():
    from domain.webhook.url_providers import cloudflare_quick_tunnel as legacy_cloudflare  # noqa: E402
    from domain.webhook.url_providers import static as legacy_static  # noqa: E402
    from domain.webhook_url_providers.cloudflare_quick_tunnel import provider as component_cloudflare  # noqa: E402
    from domain.webhook_url_providers.static import provider as component_static  # noqa: E402

    assert legacy_cloudflare is component_cloudflare
    assert legacy_static is component_static
    assert legacy_cloudflare.CloudflareQuickTunnelProvider is component_cloudflare.CloudflareQuickTunnelProvider
    assert legacy_static.StaticWebhookUrlProvider is component_static.StaticWebhookUrlProvider
