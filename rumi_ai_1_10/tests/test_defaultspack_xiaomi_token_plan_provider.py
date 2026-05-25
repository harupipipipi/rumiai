from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_xiaomi_token_plan_provider_uses_api_key_header(monkeypatch):
    from domain.ai_client.providers.xiaomi_mimo_token_plan_provider import XiaomiMimoTokenPlanSgpProvider

    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token")
    provider = XiaomiMimoTokenPlanSgpProvider()

    headers = provider._headers()

    assert headers["api-key"] == "test-token"
    assert "Authorization" not in headers


def test_xiaomi_token_plan_provider_passes_openai_tools(monkeypatch):
    from domain.ai_client.providers.xiaomi_mimo_token_plan_provider import XiaomiMimoTokenPlanSgpProvider

    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token")
    provider = XiaomiMimoTokenPlanSgpProvider()
    captured = {}
    tool = {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    }

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "I should call the write tool.",
                        "tool_calls": [
                            {
                                "id": "call_write",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": "{\"path\":\"demo.txt\",\"content\":\"ok\"}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        response = provider.complete(
            "mimo-v2.5-pro",
            [{"role": "user", "content": "Call the tool."}],
            [tool],
            {"tool_choice": {"type": "function", "function": {"name": "write_file"}}},
        )

    assert captured["path"] == "/chat/completions"
    assert captured["body"]["model"] == "mimo-v2.5-pro"
    assert captured["body"]["tools"] == [tool]
    assert captured["body"]["tool_choice"]["function"]["name"] == "write_file"
    assert response["content"][1]["type"] == "tool_use"
    assert response["content"][1]["name"] == "write_file"
    assert response["reasoning_content"] == "I should call the write tool."
    assert response["metadata"]["thinking"]["transcript"] == "I should call the write tool."

    followup_messages = provider.build_request(
        [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "I should call the write tool.",
                "tool_calls": [
                    {
                        "id": "call_write",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": "{\"path\":\"demo.txt\",\"content\":\"ok\"}",
                        },
                    }
                ],
            },
        ]
    )
    assert followup_messages[0]["reasoning_content"] == "I should call the write tool."


def test_xiaomi_token_plan_omni_passes_openai_image_messages(monkeypatch):
    from domain.ai_client.providers.xiaomi_mimo_token_plan_provider import XiaomiMimoTokenPlanSgpProvider

    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token")
    provider = XiaomiMimoTokenPlanSgpProvider()
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        provider.complete(
            "mimo-v2-omni",
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Read the image."},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aaa"}},
                        {"type": "image", "source": {"media_type": "image/jpeg", "data": "bbb"}},
                    ],
                }
            ],
            [],
            {},
        )

    assert captured["path"] == "/chat/completions"
    assert captured["body"]["model"] == "mimo-v2-omni"
    assert captured["body"]["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Read the image."},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aaa"}},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,bbb"}},
            ],
        }
    ]


def test_xiaomi_token_plan_models_are_tool_capable(monkeypatch):
    from domain.ai_client.providers.xiaomi_mimo_token_plan_provider import XiaomiMimoTokenPlanSgpProvider

    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token")
    models = {item["id"]: item for item in XiaomiMimoTokenPlanSgpProvider().list_models()}

    pro = models["xiaomi-token-plan-sgp/mimo-v2.5-pro"]
    omni = models["xiaomi-token-plan-sgp/mimo-v2-omni"]

    assert pro["type"] == "reasoning"
    assert pro["defaults"]["chat"] is True
    assert pro["capabilities"]["tool_calls"] is True
    assert pro["metadata"]["tool_call_type"] == "openai"
    assert omni["type"] == "chat"
    assert omni["defaults"]["vision"] is True
    assert omni["capabilities"]["vision"] is True
    assert omni["supports_vision"] is True
    assert omni["supports_image_input"] is True
