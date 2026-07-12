from __future__ import annotations

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.contract


def test_route_model_block_maps_flow_style_inputs(monkeypatch):
    import blocks.ai.route_model as route_model

    captured = {}

    def fake_route_model_request(request):
        captured["request"] = request
        return SimpleNamespace(to_dict=lambda: {"selected_model": request.preferred_model})

    monkeypatch.setattr(
        route_model,
        "route_model_request",
        fake_route_model_request,
    )
    monkeypatch.setattr(
        route_model.ModelRuntimeSettingsService,
        "get_settings",
        lambda self: {
            "preferred_model": "stub/default",
            "preferred_model_group": "default",
            "auto_route_within_group": True,
        },
    )

    result = route_model.run(
        {
            "conversation_id": "conv-1",
            "message": {"role": "user", "content": [{"type": "text", "text": "review this harness"}]},
            "modalities": {"has_images": False, "has_files": True},
            "tools": [{"name": "coding_file_read"}, {"tool_id": "coding_git_diff"}],
            "preferred_model": "xiaomi-token-plan-sgp/mimo-v2.5-pro",
            "requested_thinking_level": "high",
        },
        {},
    )

    assert result["status"] == "ok"
    request = captured["request"]
    assert request.conversation_id == "conv-1"
    assert request.user_text == "review this harness"
    assert request.has_images is False
    assert request.has_files is True
    assert request.requested_tools == ["coding_file_read", "coding_git_diff"]
    assert request.requires_tool_calling is True
    assert request.preferred_model == "xiaomi-token-plan-sgp/mimo-v2.5-pro"
    assert request.requested_thinking_level == "high"
    assert request.settings["preferred_model"] == "stub/default"
