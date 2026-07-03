from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
SURFACES_ROOT = ROOT / "ecosystem" / "rumi_workspace_surfaces"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))
sys.path.insert(0, str(SURFACES_ROOT))


def _provider(monkeypatch):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    return OpencodeZenProvider()


def _mock_openai_completion(provider, text: str):
    def fake_request_json(path, body):
        assert path == "/v1/chat/completions"
        assert body["model"] == "mimo-v2.5-free"
        return {
            "id": "chatcmpl_surface",
            "model": "mimo-v2.5-free",
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
        }

    return patch.object(provider, "_request_json", side_effect=fake_request_json)


def test_mimo_text_completion_can_open_slide_surface(monkeypatch):
    from surface_helpers import open_surface

    provider = _provider(monkeypatch)
    slide_text = "# Roadmap\n\n## Slide 1\n- Ship OpenCode Zen Mimo\n\n## Slide 2\n- Open the slide surface"

    with _mock_openai_completion(provider, slide_text):
        result = provider.complete(
            "opencode-zen/mimo-v2.5-free",
            [{"role": "user", "content": "Draft a two-slide outline."}],
            [],
            {"max_tokens": 512},
        )

    generated_text = result["content"][0]["text"]
    surface_result = open_surface(
        "slide",
        {"text": generated_text, "resource_id": "slide:mimo-roadmap"},
        {"conversation_id": "conv-mimo"},
    )

    surface = surface_result["data"]["surface"]
    assert surface["kind"] == "slide"
    assert surface["renderer"] == "rumi_workspace_surfaces.slide"
    assert surface["payload"]["initial_text"] == slide_text
    assert surface_result["data"]["effects"][0]["type"] == "surface.open"


def test_mimo_json_completion_can_open_movie_surface_and_create_export_render_plans(monkeypatch):
    from surface_helpers import movie_export_project, movie_render_project, open_surface

    provider = _provider(monkeypatch)
    movie_payload = {
        "text": "Launch movie brief",
        "resource_id": "movie:mimo-launch",
        "movie_project": {
            "project_id": "movie:mimo-launch",
            "title": "Mimo Launch",
            "brief": "A concise product launch movie.",
            "assets": [
                {
                    "id": "asset-1",
                    "name": "Opening card",
                    "kind": "video",
                    "mime_type": "video/mp4",
                    "source": "generated:opening-card",
                    "duration": 4.0,
                }
            ],
            "clips": [
                {
                    "id": "clip-1",
                    "name": "Opening",
                    "asset_id": "asset-1",
                    "track": "video",
                    "duration": 4.0,
                }
            ],
            "captions": [{"id": "caption-1", "text": "Mimo is ready.", "start": 0.25, "duration": 2.0}],
        },
    }

    with _mock_openai_completion(provider, json.dumps(movie_payload)):
        result = provider.complete(
            "opencode-zen/mimo-v2.5-free",
            [{"role": "user", "content": "Return a movie surface project as JSON."}],
            [],
            {"response_format": {"type": "json_object"}},
        )

    surface_args = json.loads(result["content"][0]["text"])
    surface_result = open_surface("movie", surface_args, {"conversation_id": "conv-mimo"})
    movie_project = surface_result["data"]["surface"]["payload"]["movie_project"]

    assert surface_result["data"]["surface"]["kind"] == "movie"
    assert movie_project["project_id"] == "movie:mimo-launch"
    assert movie_project["timeline"]["duration"] == 4.0
    assert "movie_export_project" in surface_result["data"]["surface"]["payload"]["operations"]
    assert "movie_render_project" in surface_result["data"]["surface"]["payload"]["operations"]

    export_result = movie_export_project({"project": movie_project}, {})
    render_result = movie_render_project({"project": movie_project}, {})

    assert export_result["status"] == "ok"
    assert export_result["data"]["export"]["filename"] == "movie-mimo-launch.json"
    assert "Opening" in export_result["data"]["export"]["timeline_edl"]
    assert render_result["status"] == "ok"
    assert render_result["data"]["render"]["output_name"] == "movie-mimo-launch.mp4"
    assert render_result["data"]["render"]["status"] in {"ready", "disabled"}
