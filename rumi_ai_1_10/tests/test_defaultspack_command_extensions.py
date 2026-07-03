from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
WORKSPACE_SURFACES_ROOT = ROOT / "ecosystem" / "rumi_workspace_surfaces"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))
sys.path.insert(0, str(WORKSPACE_SURFACES_ROOT))

MOVIE_OPERATION_FUNCTIONS = {
    "movie_import_media",
    "movie_edit_timeline",
    "movie_trim_clip",
    "movie_split_clip",
    "movie_update_captions",
    "movie_save_project",
    "movie_export_project",
    "movie_render_project",
}


def test_workspace_surface_commands_load_from_sibling_pack():
    from domain.frontend.command_registry import SlashCommandRegistry

    registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
    commands = {command["id"]: command for command in registry.list_commands()}

    for command_id, category in {
        "write": "write",
        "image": "image",
        "slide": "slide",
        "movie": "movie",
    }.items():
        command = commands[command_id]
        assert command["category"] == category
        assert command["source_pack_id"] == "rumi_workspace_surfaces"
        assert command["trust_level"] == "activated_pack"
        assert command["execution"]["type"] == "rumi_function"
        assert command["execution"]["pack_id"] == "rumi_workspace_surfaces"
        assert command["execution"]["function_id"] == f"open_{command_id}_surface"
        assert command["args"][0]["capture"] == "rest"


def test_workspace_surface_command_executes_as_owning_pack_and_returns_effects():
    from domain.frontend.command_registry import SlashCommandRegistry

    effect = {
        "type": "surface.open",
        "surface": {
            "id": "write:conv-1",
            "kind": "write",
            "title": "Write",
            "sourcePackId": "rumi_workspace_surfaces",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function") as invoke_function:
        invoke_function.return_value = {
            "status": "ok",
            "data": {"message": "opened", "effects": [effect]},
        }
        result = SlashCommandRegistry(DEFAULTSPACK_ROOT).execute(
            {
                "command": "write",
                "mode": "chat",
                "conversation_id": "conv-1",
                "args": {"text": "draft a note"},
            },
            {},
        )

    assert result["status"] == "ok"
    assert result["data"]["effects"] == [effect]
    assert result["data"]["message"] == "opened"
    invoke_function.assert_called_once()
    qualified_name, args, _context = invoke_function.call_args.args[:3]
    assert qualified_name == "rumi_workspace_surfaces:open_write_surface"
    assert args["text"] == "draft a note"
    assert args["conversation_id"] == "conv-1"
    assert invoke_function.call_args.kwargs["principal_id"] == "rumi_workspace_surfaces"
    assert Path(invoke_function.call_args.kwargs["function_pack_root"]).name == "rumi_workspace_surfaces"


class _RegistryContainer:
    def __init__(self, registry):
        self.registry = registry

    def get_or_none(self, name):
        if name == "function_registry":
            return self.registry
        return None


def test_workspace_surface_pack_registers_movie_operation_functions():
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_pack_functions_registered

    registry = FunctionRegistry()
    registered = ensure_pack_functions_registered(
        "rumi_workspace_surfaces",
        WORKSPACE_SURFACES_ROOT,
        _RegistryContainer(registry),
    )

    assert registered >= len(MOVIE_OPERATION_FUNCTIONS)
    for function_id in MOVIE_OPERATION_FUNCTIONS:
        entry = registry.get(f"rumi_workspace_surfaces:{function_id}")
        assert entry is not None
        assert entry.calling_convention == "subprocess"
        assert entry.host_execution is False


def test_movie_surface_payload_and_operations_are_editable():
    from surface_helpers import (
        MOVIE_OPERATIONS,
        movie_export_project,
        movie_import_media,
        movie_render_project,
        movie_save_project,
        movie_split_clip,
        movie_trim_clip,
        movie_update_captions,
        open_surface,
    )

    opened = open_surface("movie", {"text": "Product intro", "conversation_id": "conv-1"}, {})
    surface = opened["data"]["surface"]
    project = surface["payload"]["movie_project"]

    assert set(MOVIE_OPERATION_FUNCTIONS).issubset(set(MOVIE_OPERATIONS))
    assert surface["payload"]["operations"] == MOVIE_OPERATIONS
    assert project["timeline"]["tracks"] == ["video", "audio", "captions"]
    assert project["clips"]

    imported = movie_import_media(
        {
            "project": project,
            "media": {"name": "B-roll demo", "kind": "video", "duration": 2.5},
        },
        {},
    )
    project = imported["data"]["project"]
    assert project["assets"][-1]["name"] == "B-roll demo"

    trimmed = movie_trim_clip(
        {"project": project, "clip_id": project["clips"][0]["id"], "duration": 2.0},
        {},
    )
    project = trimmed["data"]["project"]
    assert project["clips"][0]["duration"] == 2.0

    split = movie_split_clip(
        {"project": project, "clip_id": project["clips"][0]["id"], "split_at": 1.0},
        {},
    )
    project = split["data"]["project"]
    assert len(project["clips"]) >= 5
    assert project["clips"][1]["id"].endswith("-split")

    captioned = movie_update_captions(
        {"project": project, "text": "A precise caption", "start": 0.5, "duration": 1.5},
        {},
    )
    project = captioned["data"]["project"]
    assert project["captions"][-1]["text"] == "A precise caption"

    saved = movie_save_project({"project": project}, {})
    assert saved["data"]["project_json"]
    exported = movie_export_project({"project": saved["data"]["project"]}, {})
    assert "timeline_edl" in exported["data"]["export"]
    rendered = movie_render_project({"project": saved["data"]["project"]}, {})
    assert rendered["data"]["render"]["status"] in {"ready", "disabled"}


def test_movie_caption_update_replaces_existing_caption_by_id():
    from surface_helpers import movie_update_captions, open_surface

    opened = open_surface("movie", {"text": "Product intro", "conversation_id": "conv-1"}, {})
    project = opened["data"]["surface"]["payload"]["movie_project"]
    caption_count = len(project["captions"])

    updated = movie_update_captions(
        {
            "project": project,
            "caption_id": "caption-1",
            "text": "Updated opening caption",
            "start": 0.75,
            "duration": 2.25,
        },
        {},
    )

    captions = updated["data"]["project"]["captions"]
    assert len(captions) == caption_count
    assert captions[0]["id"] == "caption-1"
    assert captions[0]["text"] == "Updated opening caption"
    assert captions[0]["start"] == 0.75
    assert captions[0]["duration"] == 2.25


def test_movie_surface_preserves_mimo_timeline_metadata():
    from surface_helpers import movie_export_project, movie_render_project, movie_save_project, open_surface

    mimo_project = {
        "title": "Mimo creative demo",
        "fps": 30,
        "duration_seconds": 16,
        "assets": [
            {
                "id": "logo",
                "type": "image",
                "placement": {"x": 0.05, "y": 0.05, "w": 0.2, "h": 0.1, "start": 0.0, "end": 16.0},
            },
            {
                "id": "demo_img",
                "type": "image",
                "placement": {"x": 0.3, "y": 0.3, "w": 0.4, "h": 0.4, "start": 5.0, "end": 10.0},
            },
        ],
        "clips": [
            {"id": "intro_clip", "start": 0.0, "end": 4.0, "source": "intro_video.mp4"},
            {"id": "workflow_clip", "start": 4.0, "end": 8.0, "source": "workflow_demo.mp4"},
            {"id": "editing_clip", "start": 8.0, "end": 12.0, "source": "editing_demo.mp4"},
            {"id": "outro_clip", "start": 12.0, "end": 16.0, "source": "outro_video.mp4"},
        ],
        "captions": [
            {"text": "ようこそ、Rumi AIへ", "start": 0.5, "end": 2.0},
            {"text": "編集を完了", "start": 14.5, "end": 16.0},
        ],
        "motion_keyframes": [
            {"target": "logo", "time": 0.0, "frame": 0, "props": {"opacity": 0.0}},
            {"target": "logo", "time": 1.0, "frame": 30, "props": {"opacity": 1.0}},
        ],
        "cuts": [
            {"time": 4.0, "type": "hard cut", "duration": 0.0},
            {"time": 8.0, "type": "fade", "duration": 0.5},
        ],
    }

    opened = open_surface(
        "movie",
        {"text": "Mimo creative demo", "movie_project": mimo_project, "resource_id": "movie:mimo-demo"},
        {},
    )

    project = opened["data"]["surface"]["payload"]["movie_project"]
    assert project["fps"] == 30
    assert project["duration_seconds"] == 16
    assert project["timeline"]["duration"] == 16.0
    assert project["assets"][0]["kind"] == "image"
    assert project["assets"][0]["placement"]["end"] == 16.0
    assert project["clips"][0]["source"] == "intro_video.mp4"
    assert project["clips"][0]["duration"] == 4.0
    assert project["clips"][-1]["end"] == 16.0
    assert project["captions"][0]["duration"] == 1.5
    assert project["captions"][0]["end"] == 2.0
    assert project["cuts"] == mimo_project["cuts"]
    assert project["motion_keyframes"] == mimo_project["motion_keyframes"]

    saved = movie_save_project({"project": project}, {})
    exported = movie_export_project({"project": saved["data"]["project"]}, {})
    rendered = movie_render_project({"project": saved["data"]["project"]}, {})
    exported_project = exported["data"]["project"]
    assert exported_project["assets"][1]["placement"]["start"] == 5.0
    assert exported_project["motion_keyframes"][1]["frame"] == 30
    assert rendered["data"]["project"]["cuts"][1]["type"] == "fade"


def test_movie_split_rejects_short_clips_and_preserves_duration_sum():
    from surface_helpers import movie_split_clip, open_surface

    opened = open_surface("movie", {"text": "Product intro", "conversation_id": "conv-1"}, {})
    project = opened["data"]["surface"]["payload"]["movie_project"]
    project["clips"][0]["duration"] = 0.5
    project["clips"][0]["out"] = 0.5

    rejected = movie_split_clip({"project": project, "clip_id": "clip-1", "split_at": 0.25}, {})

    assert rejected["status"] == "error"
    assert rejected["error"]["code"] == "CLIP_TOO_SHORT"

    project["clips"][0]["duration"] = 2.0
    project["clips"][0]["out"] = 2.0
    before_duration = sum(clip["duration"] for clip in project["clips"])

    split = movie_split_clip({"project": project, "clip_id": "clip-1", "split_at": 0.75}, {})

    assert split["status"] == "ok"
    clips = split["data"]["project"]["clips"]
    assert clips[0]["duration"] == 0.75
    assert clips[1]["duration"] == 1.25
    assert sum(clip["duration"] for clip in clips) == before_duration
