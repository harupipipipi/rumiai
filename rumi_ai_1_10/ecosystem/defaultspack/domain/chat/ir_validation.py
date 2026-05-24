from __future__ import annotations

from domain.chat.ir import RumiChatIR
from domain.chat.ir_blocks import IR_SCHEMA_VERSION


class RumiIRValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_ir(ir: RumiChatIR, *, raise_on_error: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(ir, RumiChatIR):
        errors.append("ir must be RumiChatIR")
    else:
        if ir.schema_version != IR_SCHEMA_VERSION:
            errors.append("unsupported schema_version: {}".format(ir.schema_version))
        for index, message in enumerate(ir.messages):
            if not message.role:
                errors.append(f"messages[{index}].role is required")
            for block_index, block in enumerate(message.content):
                if not block.type:
                    errors.append(f"messages[{index}].content[{block_index}].type is required")
                if block.type == "tool_call" and block.tool_call is None:
                    errors.append(f"messages[{index}].content[{block_index}].tool_call is required")
                if block.type == "tool_result" and block.tool_result is None:
                    errors.append(f"messages[{index}].content[{block_index}].tool_result is required")
    if errors and raise_on_error:
        raise RumiIRValidationError(errors)
    return errors


def normalize_ir(ir: RumiChatIR) -> RumiChatIR:
    for message in ir.messages:
        message.schema_version = IR_SCHEMA_VERSION
        message.role = str(message.role or "user")
        for block in message.content:
            block.schema_version = IR_SCHEMA_VERSION
            block.type = str(block.type or "unknown")
    ir.schema_version = IR_SCHEMA_VERSION
    return ir
