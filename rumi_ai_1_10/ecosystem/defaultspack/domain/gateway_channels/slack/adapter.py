from __future__ import annotations

from domain.gateway.channels.base import ChannelAdapter


class SlackChannel(ChannelAdapter):
    channel = "slack"
