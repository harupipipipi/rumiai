from __future__ import annotations

import json
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

SURFACE_OPERATION_FUNCTIONS = MOVIE_OPERATION_FUNCTIONS | {
    "image_export",
    "slide_save_project",
    "slide_export_deck",
}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def test_deepthink_command_falls_back_to_builtin_when_function_missing(tmp_path):
    from domain.frontend.command_registry import SlashCommandRegistry

    pack_root = tmp_path / "defaultspack"
    _write_json(
        pack_root / "commands" / "default_commands.json",
        [
            {
                "id": "deepthink",
                "name": "deepthink",
                "modes": ["chat"],
                "risk": "medium",
                "args": [{"name": "enabled", "type": "boolean", "required": False}],
                "execution": {
                    "type": "rumi_function",
                    "qualified_name": "defaultspack:ai_set_deepthink_enabled",
                },
            }
        ],
    )

    with patch("domain.function_runtime.bridge.invoke_function") as invoke_function:
        invoke_function.return_value = {
            "status": "error",
            "error": {"code": "FUNCTION_NOT_FOUND", "message": "missing"},
        }
        result = SlashCommandRegistry(pack_root).execute(
            {"command": "deepthink", "mode": "chat", "args": {"enabled": "on"}},
            {},
        )

    assert result["status"] == "ok"
    assert result["data"]["executed"] is True
    assert result["data"]["result"]["enabled"] is True
    assert result["data"]["message"]
    invoke_function.assert_called_once()


def test_function_returned_effects_are_not_templated(tmp_path):
    from domain.frontend.command_registry import SlashCommandRegistry

    pack_root = tmp_path / "defaultspack"
    _write_json(
        pack_root / "commands" / "default_commands.json",
        [
            {
                "id": "effectful",
                "name": "effectful",
                "modes": ["chat"],
                "args": [{"name": "text", "type": "string", "required": True}],
                "execution": {
                    "type": "rumi_function",
                    "qualified_name": "defaultspack:ai_set_thinking_level",
                    "effects": [
                        {
                            "type": "surface.open",
                            "surface": {
                                "id": "manifest:{command_id}:{result.value}:{arg.text}",
                                "title": "{command_id}",
                            },
                        }
                    ],
                },
            }
        ],
    )
    returned_effect = {
        "type": "surface.open",
        "surface": {
            "id": "{command_id}",
            "title": "literal {command_id}",
            "payload": {"text": "keep {command_id} untouched"},
        },
    }

    with patch("domain.function_runtime.bridge.invoke_function") as invoke_function:
        invoke_function.return_value = {
            "status": "ok",
            "data": {"value": "returned", "effects": [returned_effect]},
        }
        result = SlashCommandRegistry(pack_root).execute(
            {"command": "effectful", "mode": "chat", "args": {"text": "hello"}},
            {},
        )

    assert result["status"] == "ok"
    effects = result["data"]["effects"]
    assert effects[0]["surface"]["id"] == "manifest:effectful:returned:hello"
    assert effects[0]["surface"]["title"] == "effectful"
    assert effects[1] == returned_effect


def test_command_registry_loads_command_manifests_from_env_extension_roots(
    tmp_path,
    monkeypatch,
):
    from domain.frontend.command_registry import SlashCommandRegistry

    pack_root = tmp_path / "env_pack"
    _write_json(pack_root / "ecosystem.json", {"pack_id": "env_pack"})
    _write_json(
        pack_root / "extensions" / "commands" / "env_command" / "manifest.json",
        {
            "id": "env-command",
            "name": "env-command",
            "modes": ["chat"],
            "execution": {"type": "frontend", "action": "env_command"},
        },
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", str(pack_root))

    commands = {
        command["id"]: command
        for command in SlashCommandRegistry(DEFAULTSPACK_ROOT).list_commands()
    }

    assert "env-command" in commands
    assert commands["env-command"]["source_pack_id"] == "env_pack"
    assert commands["env-command"]["trust_level"] == "activated_pack"


class _RegistryContainer:
    def __init__(self, registry):
        self.registry = registry

    def get_or_none(self, name):
        if name == "function_registry":
            return self.registry
        return None


def test_workspace_surface_pack_registers_surface_operation_functions():
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_pack_functions_registered

    registry = FunctionRegistry()
    registered = ensure_pack_functions_registered(
        "rumi_workspace_surfaces",
        WORKSPACE_SURFACES_ROOT,
        _RegistryContainer(registry),
    )

    assert registered >= len(SURFACE_OPERATION_FUNCTIONS)
    for function_id in SURFACE_OPERATION_FUNCTIONS:
        entry = registry.get(f"rumi_workspace_surfaces:{function_id}")
        assert entry is not None
        assert entry.calling_convention == "subprocess"
        assert entry.host_execution is False


def test_workspace_surface_command_manifests_match_registered_operations():
    command_root = WORKSPACE_SURFACES_ROOT / "extensions" / "commands"
    expected_operations = {
        "image": ["image_export"],
        "slide": ["slide_save_project", "slide_export_deck"],
        "movie": [
            "movie_import_media",
            "movie_edit_timeline",
            "movie_trim_clip",
            "movie_split_clip",
            "movie_update_captions",
            "movie_save_project",
            "movie_export_project",
            "movie_render_project",
        ],
    }

    for command_id, operations in expected_operations.items():
        manifest = json.loads(
            (command_root / command_id / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["execution"] == {
            "type": "rumi_function",
            "pack_id": "rumi_workspace_surfaces",
            "function_id": f"open_{command_id}_surface",
        }
        assert manifest["ui"]["operations"] == operations
        assert set(operations).issubset(SURFACE_OPERATION_FUNCTIONS)


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

    opened = open_surface(
        "movie",
        {
            "text": "Product intro",
            "conversation_id": "conv-1",
            "attached_files": [
                {
                    "id": "opening-video",
                    "name": "opening-video.mp4",
                    "mime_type": "video/mp4",
                    "sourcePath": "/media/opening-video.mp4",
                    "duration": 4.0,
                }
            ],
        },
        {},
    )
    surface = opened["data"]["surface"]
    project = surface["payload"]["movie_project"]

    assert set(MOVIE_OPERATION_FUNCTIONS).issubset(set(MOVIE_OPERATIONS))
    assert surface["payload"]["operations"] == MOVIE_OPERATIONS
    assert project["timeline"]["tracks"] == ["video"]
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
    assert len(project["clips"]) == 3
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


def test_movie_surface_uses_attached_files_when_project_is_missing():
    from surface_helpers import open_surface

    attached_files = [
        {
            "id": "selected-video",
            "name": "selected-video.mp4",
            "mime_type": "video/mp4",
            "sourcePath": "/tmp/selected-video.mp4",
            "duration": 8.5,
        },
        {
            "id": "selected-audio",
            "name": "selected-audio.wav",
            "mime_type": "audio/wav",
            "path": "/tmp/selected-audio.wav",
            "duration": 12.0,
        },
    ]

    opened = open_surface(
        "movie",
        {
            "text": "Use the selected media",
            "resource_id": "movie:selected-media",
            "attached_files": attached_files,
        },
        {},
    )

    project = opened["data"]["surface"]["payload"]["movie_project"]
    asset_ids = {asset["id"] for asset in project["assets"]}

    assert [asset["id"] for asset in project["assets"]] == ["selected-video", "selected-audio"]
    assert project["assets"][0]["kind"] == "video"
    assert project["assets"][0]["source"] == "/tmp/selected-video.mp4"
    assert project["assets"][1]["kind"] == "audio"
    assert project["assets"][1]["source"] == "/tmp/selected-audio.wav"
    assert all(not str(asset["source"]).startswith("generated:") for asset in project["assets"])
    assert {clip["asset_id"] for clip in project["clips"]}.issubset(asset_ids)


def test_movie_surface_parses_generated_json_project_from_text():
    from surface_helpers import open_surface

    generated_text = "/movie " + json.dumps(
        {
            "text": "A launch teaser for makers.",
            "movie_project": {
                "title": "Maker launch teaser",
                "assets": [
                    {
                        "id": "hero-video",
                        "name": "Hero capture",
                        "kind": "video",
                        "source": "/media/hero-video.mp4",
                        "duration": 3.5,
                    }
                ],
                "clips": [
                    {
                        "id": "hero-clip",
                        "name": "Open on the product",
                        "asset_id": "hero-video",
                        "duration": 3.5,
                    }
                ],
                "captions": [
                    {
                        "id": "caption-open",
                        "text": "Build faster with Rumi.",
                        "start": 0.2,
                        "duration": 2.0,
                    }
                ],
            },
        }
    )

    opened = open_surface(
        "movie",
        {"text": generated_text, "resource_id": "movie:json-text"},
        {},
    )
    project = opened["data"]["surface"]["payload"]["movie_project"]

    assert project["project_id"] == "movie:json-text"
    assert project["title"] == "Maker launch teaser"
    assert project["brief"] == "A launch teaser for makers."
    assert [asset["source"] for asset in project["assets"]] == ["/media/hero-video.mp4"]
    assert all(not str(asset["source"]).startswith("generated:") for asset in project["assets"])
    assert [clip["id"] for clip in project["clips"]] == ["hero-clip"]
    assert project["clips"][0]["name"] == "Open on the product"
    assert project["captions"][0]["text"] == "Build faster with Rumi."
    assert project["timeline"]["duration"] == 3.5


def test_movie_surface_parses_top_level_generated_json_project_from_text():
    from surface_helpers import open_surface

    generated_text = json.dumps(
        {
            "title": "Top-level movie plan",
            "brief": "Use the provided media plan directly.",
            "assets": [
                {
                    "id": "screen-recording",
                    "name": "Screen recording",
                    "kind": "video",
                    "source": "/media/screen-recording.mp4",
                    "duration": 2.25,
                }
            ],
            "clips": [
                {
                    "id": "screen-clip",
                    "name": "Show the workflow",
                    "asset_id": "screen-recording",
                    "duration": 2.25,
                }
            ],
            "captions": [
                {
                    "id": "caption-1",
                    "text": "Everything stays editable.",
                    "start": 0.1,
                    "end": 1.6,
                }
            ],
        }
    )

    opened = open_surface(
        "movie",
        {"text": generated_text, "resource_id": "movie:top-level-json"},
        {},
    )
    project = opened["data"]["surface"]["payload"]["movie_project"]

    assert project["project_id"] == "movie:top-level-json"
    assert project["title"] == "Top-level movie plan"
    assert [asset["id"] for asset in project["assets"]] == ["screen-recording"]
    assert [clip["id"] for clip in project["clips"]] == ["screen-clip"]
    assert project["clips"][0]["asset_id"] == "screen-recording"
    assert project["captions"][0]["text"] == "Everything stays editable."
    assert project["captions"][0]["duration"] == 1.5
    assert project["timeline"]["duration"] == 2.25
    assert "{" not in project["title"]
    assert "{" not in project["brief"]


def test_slide_surface_derives_project_from_text_and_attached_files():
    from surface_helpers import open_surface

    attached_files = [
        {
            "id": "customer-chart",
            "name": "customer-chart.png",
            "mime_type": "image/png",
            "sourcePath": "/tmp/customer-chart.png",
        },
        {
            "id": "research-notes",
            "name": "research-notes.pdf",
            "mime_type": "application/pdf",
            "path": "/tmp/research-notes.pdf",
        },
    ]

    opened = open_surface(
        "slide",
        {
            "text": "# Customer update\n\n## Slide 1\n- Revenue is growing\n\n## Slide 2\n- Expand onboarding",
            "resource_id": "slide:customer-update",
            "attached_files": attached_files,
        },
        {"conversation_id": "conv-slide"},
    )

    surface = opened["data"]["surface"]
    project = surface["payload"]["slide_project"]

    assert surface["kind"] == "slide"
    assert project["project_id"] == "slide:customer-update"
    assert project["title"] == "Customer update"
    assert [slide["title"] for slide in project["slides"]][:2] == ["Slide 1", "Slide 2"]
    assert project["slides"][0]["bullets"] == ["Revenue is growing"]
    assert project["slides"][0]["asset_ids"] == ["customer-chart"]
    assert project["slides"][1]["asset_ids"] == ["research-notes"]
    assert project["assets"][0]["kind"] == "image"
    assert project["assets"][1]["kind"] == "document"
    assert project["status_cards"][0]["label"] == "Slides"
    assert project["export"]["filename"] == "slide-customer-update.pptx"


def test_slide_surface_accepts_generated_json_deck_payload():
    from surface_helpers import open_surface

    deck_payload = {
        "text": "Launch narrative",
        "resource_id": "slide:mimo-launch",
        "slide_project": {
            "project_id": "slide:mimo-launch",
            "title": "Mimo Launch Deck",
            "theme": {"name": "Launch dark", "ratio": "16:9"},
            "assets": [{"id": "hero", "name": "hero.png", "kind": "image", "source": "/assets/hero.png"}],
            "slides": [
                {
                    "id": "intro",
                    "title": "Launch story",
                    "subtitle": "Why now",
                    "bullets": ["Fast setup", "Local first"],
                    "notes": "Open with the user outcome.",
                    "asset_ids": ["hero"],
                }
            ],
            "export": {"format": "pdf", "filename": "mimo-launch.pdf", "status": "planned"},
        },
    }

    opened = open_surface("slide", deck_payload, {"conversation_id": "conv-mimo"})
    project = opened["data"]["surface"]["payload"]["slide_project"]

    assert project["title"] == "Mimo Launch Deck"
    assert project["theme"]["name"] == "Launch dark"
    assert project["slides"][0]["id"] == "intro"
    assert project["slides"][0]["bullets"] == ["Fast setup", "Local first"]
    assert project["slides"][0]["asset_ids"] == ["hero"]
    assert project["assets"][0]["source"] == "/assets/hero.png"
    assert project["export"]["filename"] == "mimo-launch.pdf"


def test_slide_surface_parses_generated_json_deck_from_text():
    from surface_helpers import open_surface

    generated_text = json.dumps(
        {
            "text": "A product story for non-technical users.",
            "slide_project": {
                "title": "No-code onboarding",
                "slides": [
                    {"title": "Describe the goal", "bullets": ["No setup required", "Mimo drafts the deck"]}
                ],
            },
        }
    )

    opened = open_surface("slide", {"text": generated_text, "resource_id": "slide:json-text"}, {})
    project = opened["data"]["surface"]["payload"]["slide_project"]

    assert project["project_id"] == "slide:json-text"
    assert project["title"] == "No-code onboarding"
    assert project["brief"] == "A product story for non-technical users."
    assert project["slides"][0]["title"] == "Describe the goal"
    assert project["slides"][0]["bullets"] == ["No setup required", "Mimo drafts the deck"]
    assert "{" not in project["title"]
    assert "{" not in project["brief"]


def test_movie_surface_preserves_embedded_mimo_json_aliases_starts_and_timeline():
    from surface_helpers import open_surface

    movie_project = {
        "title": "Mimo nine clip launch",
        "brief": "Mimo launch brief",
        "fps": 24,
        "timeline": {
            "duration": 42.5,
            "tracks": ["video", "audio", "captions"],
            "metadata": {"source": "mimo", "schema_version": 3},
        },
        "assets": [
            {
                "asset_id": "hero-video",
                "name": "Hero video",
                "type": "video/mp4",
                "path": "/media/hero-video.mp4",
                "duration": 9.0,
            },
            {
                "asset_id": "launch-audio",
                "name": "Launch audio",
                "type": "audio/mpeg",
                "url": "https://cdn.example.test/launch.mp3",
                "duration": 42.5,
            },
        ],
        "clips": [
            {
                "id": f"clip-{index}",
                "name": f"Scene {index}",
                "assetId": "hero-video",
                "source": "/media/hero-video.mp4",
                "start": (index - 1) * 4.5,
                "duration": 4.5,
            }
            for index in range(1, 10)
        ],
        "captions": [
            {
                "id": f"caption-{index}",
                "text": f"Caption {index}",
                "start": index * 2.0,
                "end": index * 2.0 + 1.25,
            }
            for index in range(16)
        ],
    }
    embedded = (
        "Here is the Mimo plan:\n```json\n"
        + json.dumps({"text": "Mimo launch brief", "movie_project": movie_project})
        + "\n```\nUse the plan as-is."
    )

    opened = open_surface(
        "movie",
        {"text": embedded, "resource_id": "movie:mimo-embedded"},
        {},
    )
    project = opened["data"]["surface"]["payload"]["movie_project"]

    assert project["title"] == "Mimo nine clip launch"
    assert project["brief"] == "Mimo launch brief"
    assert len(project["clips"]) == 9
    assert [clip["start"] for clip in project["clips"]] == [index * 4.5 for index in range(9)]
    assert {clip["asset_id"] for clip in project["clips"]} == {"hero-video"}
    assert project["assets"][0]["id"] == "hero-video"
    assert project["assets"][0]["source"] == "/media/hero-video.mp4"
    assert project["assets"][1]["id"] == "launch-audio"
    assert project["assets"][1]["source"] == "https://cdn.example.test/launch.mp3"
    assert len(project["captions"]) == 16
    assert [caption["start"] for caption in project["captions"]] == [index * 2.0 for index in range(16)]
    assert project["timeline"]["duration"] == 42.5
    assert project["timeline"]["metadata"] == {"source": "mimo", "schema_version": 3}
    assert "{" not in project["title"]
    assert "```" not in project["brief"]


def test_image_surface_parses_structured_project_with_real_variants_and_assets():
    from surface_helpers import open_surface

    embedded = json.dumps(
        {
            "text": "Product image brief",
            "image_project": {
                "project_id": "image:mimo-product",
                "prompt": "A product image on a clean desk",
                "mode": "edit",
                "assets": [
                    {
                        "asset_id": "source-photo",
                        "name": "source-photo.png",
                        "type": "image/png",
                        "path": "/assets/source-photo.png",
                    }
                ],
                "variants": [
                    {
                        "id": "variant-clean",
                        "label": "Clean crop",
                        "status": "ready",
                        "asset_id": "source-photo",
                        "source": "/assets/variant-clean.webp",
                        "mime_type": "image/webp",
                    }
                ],
            },
        }
    )

    opened = open_surface(
        "image",
        {"text": f"Mimo result:\n{embedded}", "resource_id": "image:mimo-product"},
        {},
    )
    project = opened["data"]["surface"]["payload"]["image_project"]

    assert project["project_id"] == "image:mimo-product"
    assert project["prompt"] == "A product image on a clean desk"
    assert project["assets"][0]["id"] == "source-photo"
    assert project["assets"][0]["source"] == "/assets/source-photo.png"
    assert project["variants"][0]["asset_id"] == "source-photo"
    assert project["variants"][0]["source"] == "/assets/variant-clean.webp"
    assert all(not str(item.get("source", "")).startswith("generated:") for item in project["assets"] + project["variants"])
    assert "{" not in project["prompt"]


def test_slide_surface_preserves_json_elements_styles_and_attached_assets_without_json_leakage():
    from surface_helpers import open_surface

    embedded = json.dumps(
        {
            "text": "Customer update brief",
            "slide_project": {
                "title": "Customer update",
                "assets": [
                    {
                        "asset_id": "chart",
                        "name": "chart.svg",
                        "type": "image/svg+xml",
                        "path": "/assets/chart.svg",
                    }
                ],
                "slides": [
                    {
                        "title": "Growth story",
                        "notes": "Mention the customer outcome.",
                        "elements": [
                            {
                                "id": "headline",
                                "type": "text",
                                "text": "Revenue is growing",
                                "x": 12,
                                "y": 8,
                                "width": 48,
                                "height": 12,
                                "style": {"color": "#123456", "fontSize": 24},
                            },
                            {
                                "id": "chart-element",
                                "type": "image",
                                "asset_id": "chart",
                                "x": 50,
                                "y": 20,
                                "width": 42,
                                "height": 60,
                            },
                        ],
                    },
                    {"title": "Attached evidence", "notes": "Use the attached source."},
                ],
            },
        }
    )
    attached_files = [
        {
            "id": "attached-evidence",
            "name": "evidence.png",
            "mime_type": "image/png",
            "sourcePath": "/assets/evidence.png",
        }
    ]

    opened = open_surface(
        "slide",
        {
            "text": f"Mimo deck:\n{embedded}",
            "resource_id": "slide:mimo-customer",
            "attached_files": attached_files,
        },
        {},
    )
    project = opened["data"]["surface"]["payload"]["slide_project"]

    assert project["title"] == "Customer update"
    assert project["slides"][0]["notes"] == "Mention the customer outcome."
    assert project["slides"][0]["elements"][0]["x"] == 12
    assert project["slides"][0]["elements"][0]["style"] == {"color": "#123456", "fontSize": 24}
    assert project["slides"][0]["elements"][1]["asset_id"] == "chart"
    assert project["slides"][1]["asset_ids"] == ["attached-evidence"]
    assert {asset["id"] for asset in project["assets"]} == {"chart", "attached-evidence"}
    assert project["assets"][0]["source"] == "/assets/chart.svg"
    assert project["assets"][1]["source"] == "/assets/evidence.png"
    assert "{" not in project["title"]
    assert "{" not in project["slides"][0]["notes"]


def test_movie_caption_update_replaces_existing_caption_by_id():
    from surface_helpers import movie_update_captions, open_surface

    opened = open_surface(
        "movie",
        {
            "text": "Product intro",
            "conversation_id": "conv-1",
            "attached_files": [
                {
                    "id": "opening-video",
                    "name": "opening-video.mp4",
                    "mime_type": "video/mp4",
                    "sourcePath": "/media/opening-video.mp4",
                    "duration": 4.0,
                }
            ],
            "movie_project": {
                "captions": [
                    {
                        "id": "caption-1",
                        "text": "Original opening caption",
                        "start": 0.0,
                        "duration": 2.0,
                    }
                ]
            },
        },
        {},
    )
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

    opened = open_surface(
        "movie",
        {
            "text": "Product intro",
            "conversation_id": "conv-1",
            "attached_files": [
                {
                    "id": "opening-video",
                    "name": "opening-video.mp4",
                    "mime_type": "video/mp4",
                    "sourcePath": "/media/opening-video.mp4",
                    "duration": 4.0,
                }
            ],
        },
        {},
    )
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


def test_surface_exports_embed_only_safe_assets_and_keep_projects_portable():
    from surface_helpers import (
        image_export,
        movie_export_project,
        movie_render_project,
        slide_export_deck,
        slide_save_project,
    )

    unsafe_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        '<script>alert(1)</script><circle cx="4" cy="4" r="3" /></svg>'
    )
    image_result = image_export(
        {"filename": "../launch image", "svg": unsafe_svg},
        {},
    )
    assert image_result["status"] == "ok"
    assert image_result["export"]["filename"] == "launch-image.svg"
    assert image_result["export"]["mime_type"] == "image/svg+xml"
    assert "script" not in image_result["export"]["source"].lower()
    assert "onload" not in image_result["export"]["source"].lower()
    assert image_export({"source": "https://unsafe.example/image.png"}, {}) == {
        "status": "error",
        "error": {
            "code": "IMAGE_EXPORT_DISABLED",
            "message": "Image export requires sanitized SVG or embedded image data.",
        },
    }

    slide_project = {
        "project_id": "slide:../launch deck",
        "title": "Launch <deck>",
        "assets": [
            {"id": "safe-art", "name": "safe.svg", "kind": "image", "source": unsafe_svg},
            {"id": "remote-art", "name": "remote.png", "kind": "image", "source": "https://unsafe.example/image.png"},
        ],
        "slides": [
            {
                "id": "opening",
                "elements": [
                    {
                        "id": "headline",
                        "type": "text",
                        "text": "Launch <now>",
                        "x": 12,
                        "y": 8,
                        "width": 48,
                        "height": 12,
                        "style": {"color": "#123456", "fontSize": 24, "background": "url(https://unsafe.example)"},
                    },
                    {
                        "id": "safe-image",
                        "type": "image",
                        "asset_id": "safe-art",
                        "x": 50,
                        "y": 20,
                        "width": 42,
                        "height": 60,
                        "style": {"objectFit": "contain"},
                    },
                    {
                        "id": "remote-image",
                        "type": "image",
                        "asset_id": "remote-art",
                        "x": 0,
                        "y": 0,
                        "width": 10,
                        "height": 10,
                    },
                ],
            }
        ],
    }
    saved = slide_save_project({"project": slide_project}, {})
    saved_element = saved["project"]["slides"][0]["elements"][0]
    assert [saved_element[key] for key in ("x", "y", "width", "height")] == [12.0, 8.0, 48.0, 12.0]
    assert saved_element["style"] == {"color": "#123456", "fontSize": 24.0}

    deck = slide_export_deck({"project": saved["project"], "filename": "../launch deck.html"}, {})
    exported = deck["export"]
    assert exported["filename"] == "launch-deck.html"
    assert "aspect-ratio:16/9" in exported["content"]
    assert "left:12.0%;top:8.0%;width:48.0%;height:12.0%" in exported["content"]
    assert "color:#123456;font-size:24.0px" in exported["content"]
    assert "data:image/svg+xml;charset=utf-8," in exported["content"]
    assert "unsafe.example" not in exported["content"]
    assert "<script>alert" not in exported["content"].lower()
    assert "onload" not in exported["content"].lower()
    editable_project = json.loads(exported["project_json"])
    assert editable_project["slides"] == saved["project"]["slides"]
    assert editable_project["assets"][0]["source"].startswith("data:image/svg+xml;charset=utf-8,")
    assert editable_project["assets"][1]["source"] == ""
    assert exported["warnings"] == [
        "Asset remote-art was omitted because it was not embedded image data."
    ]

    movie_project = {
        "project_id": "movie:../launch cut",
        "clips": [{"id": "clip-1", "name": "Opening", "start": 61.25, "duration": 2.75, "track": "video"}],
        "captions": [{"id": "caption-1", "text": "After a minute", "start": 61.25, "duration": 2.75}],
    }
    movie_export = movie_export_project({"project": movie_project}, {})["data"]["export"]
    assert movie_export["filename"] == "movie-launch-cut.json"
    assert "00:01:01.250 --> 00:01:04.000" in movie_export["captions_vtt"]
    assert "Opening" in movie_export["timeline_edl"]
    assert movie_export["timeline_filename"] == "movie-launch-cut-timeline.edl"
    assert movie_export["captions_filename"] == "movie-launch-cut-captions.vtt"
    render = movie_render_project({"project": movie_project}, {})["data"]["render"]
    assert render["status"] == "disabled"
    assert render["enabled"] is False
    assert render["engine"] == "unavailable"
    assert "ffmpeg" not in render["message"].lower()
