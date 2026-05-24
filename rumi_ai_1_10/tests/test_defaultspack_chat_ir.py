from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_stored_messages_to_ir_preserves_message_fields_and_unknown_blocks():
    from domain.chat.ir_blocks import IR_SCHEMA_VERSION
    from domain.chat.ir_legacy_adapter import stored_messages_to_ir
    from domain.chat.ir_validation import validate_ir

    ir = stored_messages_to_ir(
        "conv-1",
        [
            {
                "id": "m1",
                "conversation_id": "conv-1",
                "parent_id": "root",
                "children_ids": ["m2"],
                "sequence_number": 3,
                "created_at": 123,
                "role": "user",
                "content": [{"type": "unknown_vendor", "payload": {"x": 1}}],
                "metadata": {"attachments": [{"id": "a1"}]},
            }
        ],
    )

    assert ir.schema_version == IR_SCHEMA_VERSION
    assert validate_ir(ir) == []
    assert ir.messages[0].id == "m1"
    assert ir.messages[0].parent_id == "root"
    assert ir.messages[0].children_ids == ["m2"]
    assert ir.messages[0].content[0].type == "unknown_vendor"
    assert ir.messages[0].content[0].original["payload"] == {"x": 1}


def test_ir_keeps_reasoning_internal_by_default():
    from domain.chat.ir import RumiChatIR, RumiIRMessage
    from domain.chat.ir_blocks import RumiIRBlock
    from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages

    ir = RumiChatIR(
        conversation_id="c",
        messages=[
            RumiIRMessage(
                role="assistant",
                content=[RumiIRBlock(type="reasoning", text="hidden", model_visible=False), RumiIRBlock(type="text", text="visible")],
            )
        ],
    )

    assert ir_to_legacy_standard_messages(ir) == [{"role": "assistant", "content": "visible"}]
