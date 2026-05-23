from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_ir_legacy_adapter_roundtrips_tool_history():
    from domain.chat.ir_legacy_adapter import (
        ir_to_legacy_standard_messages,
        ir_to_stored_messages,
        stored_messages_to_ir,
    )

    stored = [
        {"id": "a", "role": "assistant", "content": [{"type": "tool_call", "id": "tc", "name": "lookup", "arguments": "{}"}]},
        {"id": "t", "role": "tool", "content": [{"type": "tool_result", "tool_call_id": "tc", "name": "lookup", "content": "ok"}]},
    ]
    ir = stored_messages_to_ir("conv", stored)

    assert ir_to_legacy_standard_messages(ir)[0]["tool_calls"][0]["function"]["name"] == "lookup"
    assert ir_to_legacy_standard_messages(ir)[1]["tool_call_id"] == "tc"
    assert ir_to_stored_messages(ir)[0]["id"] == "a"


def test_legacy_standard_messages_to_ir_preserves_images_and_tools():
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    ir = legacy_standard_messages_to_ir(
        [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]},
            {"role": "tool", "tool_call_id": "tc", "name": "lookup", "content": "ok"},
        ],
        conversation_id="conv",
    )

    assert ir.messages[0].content[0].type == "image_url"
    assert ir.messages[1].content[0].tool_result.tool_call_id == "tc"
