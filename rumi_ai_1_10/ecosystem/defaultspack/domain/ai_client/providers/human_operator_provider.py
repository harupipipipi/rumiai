from __future__ import annotations

import json
from typing import Any

from blocks._common import gen_id
from domain.ai_client.base_provider import BaseProvider
from domain.human_operator.constants import HUMAN_OPERATOR_MODEL, HUMAN_OPERATOR_TOOL_NAME


class HumanOperatorProvider(BaseProvider):
    """Local command-only provider that opens a manual canvas session."""

    provider_id = "human-operator"

    def complete(self, model, messages, tools, params):
        return self._response(model, messages, tools, params)

    def stream(self, model, messages, tools, params):
        response = self._response(model, messages, tools, params)
        tool_uses = [
            block
            for block in (response.get("content") or [])
            if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_call"}
        ]
        if tool_uses:
            for block in tool_uses:
                arguments = json.dumps(block.get("input") or {}, ensure_ascii=False)
                yield {"type": "tool_call_start", "id": block.get("id", ""), "name": block.get("name", "")}
                yield {
                    "type": "tool_call_delta",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments_chunk": arguments,
                }
                yield {"type": "tool_call_end", "id": block.get("id", ""), "name": block.get("name", "")}
            yield {
                "type": "stream_end",
                "finish_reason": response.get("finish_reason", "tool_calls"),
                "usage": response.get("usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
            }
            return
        text = self._response_text(response)
        if text:
            yield {"type": "content_delta", "delta": {"type": "text", "text": text}}
        yield {
            "type": "stream_end",
            "finish_reason": response.get("finish_reason", "stop"),
            "usage": response.get("usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
        }

    def embed(self, model, input_text):
        raise NotImplementedError("human-operator provider does not support embeddings")

    def image_gen(self, model, prompt, params):
        raise NotImplementedError("human-operator provider does not support image generation")

    def image_analyze(self, model, image, prompt):
        raise NotImplementedError("human-operator provider does not support image analysis")

    def transcribe(self, model, audio, params):
        raise NotImplementedError("human-operator provider does not support transcription")

    def tts(self, model, text, voice):
        raise NotImplementedError("human-operator provider does not support text-to-speech")

    def _response(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], params: dict[str, Any]):
        del model
        if self._last_tool_result_is_human_operator_canvas(messages):
            return self._text_response(
                "Human Operator Canvas opened. Use the canvas to append user input and AI output by hand."
            )

        command = self._last_user_command(messages)
        if command == "/help":
            return self._text_response(
                "This model is command-only.\n"
                "- /start : open a fresh Human Operator Canvas session\n"
                "- /help : show this help\n\n"
                "Normal chat text is rejected so one human can play both sides from the canvas."
            )

        if command.startswith("/start"):
            tool_name = self._tool_name_from_provider_tools(tools)
            if not tool_name:
                return self._text_response(
                    "Human Operator Canvas tool is unavailable for this turn. Check tool policy or model routing and try again."
                )
            note = command.partition(" ")[2].strip()
            arguments = {
                "session_id": gen_id("humanop_"),
                "command": command,
                "note": note,
                "model": HUMAN_OPERATOR_MODEL,
                "messages": messages,
                "params": params if isinstance(params, dict) else {},
                "tool_names": self._provider_tool_names(tools),
            }
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "id": gen_id("toolcall_"),
                        "name": tool_name,
                        "input": arguments,
                    }
                ],
                "finish_reason": "tool_calls",
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "metadata": {"command_only": True, "human_operator": True},
            }

        return self._text_response(
            "This model only accepts commands. Use /start to open Human Operator Canvas or /help for details."
        )

    @staticmethod
    def _text_response(text: str) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": text}],
            "finish_reason": "stop",
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "metadata": {"command_only": True, "human_operator": True},
        }

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        blocks = response.get("content") if isinstance(response, dict) else []
        if not isinstance(blocks, list):
            return ""
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)

    @staticmethod
    def _provider_tool_names(tools: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for tool in tools if isinstance(tools, list) else []:
            function_def = tool.get("function") if isinstance(tool, dict) else {}
            name = str(function_def.get("name") or tool.get("name") or "").strip() if isinstance(function_def, dict) else ""
            if name:
                names.append(name)
        return names

    @staticmethod
    def _tool_name_from_provider_tools(tools: list[dict[str, Any]]) -> str:
        for name in HumanOperatorProvider._provider_tool_names(tools):
            if name == HUMAN_OPERATOR_TOOL_NAME:
                return name
        return ""

    @staticmethod
    def _last_user_command(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages if isinstance(messages, list) else []):
            if not isinstance(message, dict) or str(message.get("role") or "") != "user":
                continue
            text = HumanOperatorProvider._message_text(message.get("content"))
            if text:
                return text.strip()
        return ""

    @staticmethod
    def _last_tool_result_is_human_operator_canvas(messages: list[dict[str, Any]]) -> bool:
        for message in reversed(messages if isinstance(messages, list) else []):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role == "tool":
                return str(message.get("name") or "") == HUMAN_OPERATOR_TOOL_NAME
            if role in {"assistant", "user"}:
                return False
        return False

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(part for part in parts if part)
