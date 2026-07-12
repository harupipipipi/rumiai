from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from blocks.p2p._helpers import error_response, settings_from
from domain.p2p.inbound import handle_inbound_envelope
from domain.p2p.peer_store import PeerStore
from domain.p2p.replay_guard import ReplayGuard


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    settings = settings_from(input_data, context)
    result = handle_inbound_envelope(
        input_data,
        context=context if isinstance(context, dict) else {},
        settings=settings,
        peer_store=PeerStore(settings.store_path),
        replay_guard=ReplayGuard(settings.store_path, ttl_seconds=settings.replay_ttl_seconds),
    )
    if result.get("status") != "ok":
        return error_response(result)
    return ok(result)
