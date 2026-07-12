from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.agent_runtime.transcript import TranscriptStore  # noqa: E402


def test_transcript_successor_keeps_parent_and_compaction_packet(tmp_path):
    store = TranscriptStore(tmp_path)
    transcript_id = store.create("run_1")
    store.append_message(transcript_id, {"role": "user", "content": "hello"})

    successor = store.create_successor(
        transcript_id,
        run_id="run_1",
        compact_id="compact_1",
        packet={"goal": "continue", "next_steps": ["answer"]},
    )

    tail = store.read_tail(successor, 5)
    assert tail[0]["type"] == "session_header"
    assert tail[0]["payload"]["parent_id"] == transcript_id
    assert tail[1]["type"] == "compaction"
    assert tail[1]["payload"]["packet"]["goal"] == "continue"
