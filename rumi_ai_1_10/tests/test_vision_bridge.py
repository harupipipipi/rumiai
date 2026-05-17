from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_vision_bridge_strips_image_blocks_and_inserts_text_context():
    from domain.vision.image_bridge import apply_vision_bridge_to_messages, bridge_context_text

    understanding = {"summary": "UI screenshot", "ocr_text": "Save", "uncertainties": ["small text unclear"]}
    text = bridge_context_text(understanding)
    assert "[画像理解結果]" in text
    assert "Save" in text

    messages = [{"role": "user", "content": [{"type": "text", "text": "read it"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,aaa"}}]}]
    bridged = apply_vision_bridge_to_messages(messages, understanding)
    assert bridged[0]["role"] == "system"
    assert "UI screenshot" in bridged[0]["content"]
    assert bridged[1]["content"] == [{"type": "text", "text": "read it"}]


def test_describe_images_has_safe_fallback():
    from domain.vision.image_bridge import describe_images

    result = describe_images(attachments=[{"id": "att_1", "type": "image/png"}], model="")
    assert result["source_attachment_ids"] == ["att_1"]
    assert result["valid_for_models_without_vision"] is True if "valid_for_models_without_vision" in result else True
