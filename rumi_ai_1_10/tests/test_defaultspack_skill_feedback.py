from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_skill_create_from_feedback_writes_valid_skill_and_dream(monkeypatch, tmp_path):
    from blocks.skill.create_from_feedback import run as create_skill
    from domain.extensions.runtime import get_extension_registry

    extensions_root = tmp_path / "extensions"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", str(extensions_root))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MEMORY2_DIR", str(tmp_path / "memory2"))

    result = create_skill(
        {
            "feedback": "次からLINE groupではメンションされた時だけ反応して",
            "name": "line mention correction",
            "triggers": ["LINE", "mention"],
            "applies_to_tools": ["line_reply"],
            "extensions_root": str(extensions_root),
            "conversation_id": "c1",
        },
        {},
    )

    assert result["status"] == "ok"
    data = result["data"]
    manifest_path = Path(data["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["category"] == "skill"
    assert manifest["triggers"] == ["LINE", "mention"]
    assert manifest["applies_to_tools"] == ["line_reply"]
    assert Path(data["dream_path"]).read_text(encoding="utf-8").count("[feedback-skill]") == 1
    skills = get_extension_registry(force_reload=True).skills().list()
    assert any(item["id"] == data["skill_id"] for item in skills)
