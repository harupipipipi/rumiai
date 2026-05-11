from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.response import RumiResponse  # noqa: E402
from domain.external.response_planner import ResponsePlanner  # noqa: E402


def test_discord_chunks_2000_chars_and_uses_safe_mentions():
    plan = ResponsePlanner("discord").plan(RumiResponse(text="a" * 2500))

    assert len(plan["messages"]) == 2
    assert len(plan["messages"][0]["text"]) == 2000
    assert plan["safe_defaults"]["allowed_mentions"] == {"parse": []}


def test_file_limits_and_sensitive_artifacts_fallback():
    plan = ResponsePlanner("discord").plan(
        RumiResponse(
            text="done",
            artifacts=[
                {"path": "/tmp/a.pdf", "mime_type": "application/pdf", "size": 999999999},
                {"path": "/tmp/secret.txt", "mime_type": "text/plain", "size": 10, "sensitivity": "secret"},
            ],
        )
    )

    assert plan["files"] == []
    assert {item["reason"] for item in plan["fallbacks"]} == {"file size limit exceeded", "sensitive artifact blocked"}


def test_line_files_disabled_fallbacks_to_text_only():
    plan = ResponsePlanner("line").plan(
        RumiResponse(text="ok", artifacts=[{"path": "/tmp/a.txt", "mime_type": "text/plain", "size": 10}])
    )

    assert plan["messages"] == [{"type": "text", "text": "ok"}]
    assert plan["files"] == []
    assert plan["fallbacks"][0]["reason"] == "files disabled"
