from __future__ import annotations

from domain.gateway.channels.base import ChannelAdapter


class LineChannel(ChannelAdapter):
    channel = "line"
