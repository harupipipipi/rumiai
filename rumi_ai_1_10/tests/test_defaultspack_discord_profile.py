from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.input_profile_engine import InputProfileEngine  # noqa: E402
from domain.external.input_profile_registry import InputProfileRegistry  # noqa: E402
from domain.external.normalizer import normalize_discord_message  # noqa: E402


def test_discord_profile_maps_content():
    event = normalize_discord_message({"id": "m1", "channel_id": "c1", "content": "hello", "author": {"id": "u1"}}, verified=True)
    profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("discord.default")
    envelope = InputProfileEngine(profile).to_envelope(event)

    assert envelope.input == "hello"
    assert envelope.source["provider"] == "discord"
