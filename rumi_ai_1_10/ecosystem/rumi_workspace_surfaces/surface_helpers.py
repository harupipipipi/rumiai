from __future__ import annotations

import json
import shutil
import time
from copy import deepcopy
from typing import Any


PACK_ID = "rumi_workspace_surfaces"


SURFACES = {
    "write": {
        "title": "Write",
        "kind": "write",
        "renderer": "rumi_workspace_surfaces.write",
        "initial_text": "# Draft\n\n",
    },
    "image": {
        "title": "Image",
        "kind": "image",
        "renderer": "rumi_workspace_surfaces.image",
        "initial_text": "Image prompt\n",
    },
    "slide": {
        "title": "Slide",
        "kind": "slide",
        "renderer": "rumi_workspace_surfaces.slide",
        "initial_text": "# Slide 1\n\nSpeaker notes...\n",
    },
    "movie": {
        "title": "Movie",
        "kind": "movie",
        "renderer": "rumi_workspace_surfaces.movie",
        "initial_text": "Movie brief\n- clip:\n- trim:\n- captions:\n",
    },
}

MOVIE_OPERATIONS = [
    "movie_import_media",
    "movie_edit_timeline",
    "movie_trim_clip",
    "movie_split_clip",
    "movie_update_captions",
    "movie_save_project",
    "movie_export_project",
    "movie_render_project",
]

MOVIE_CLIP_COLORS = ["sky", "violet", "emerald", "amber", "rose", "cyan"]


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def _first_title_line(text: str, fallback: str) -> str:
    for line in str(text or "").splitlines():
        cleaned = line.replace("#", " ").replace("-", " ").strip()
        if cleaned:
            return cleaned[:96]
    return fallback


def _number(value: Any, fallback: float, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = fallback
    if minimum is not None:
        result = max(minimum, result)
    return round(result, 3)


def _asset_from_attached(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _clean_text(item.get("name") or item.get("path") or item.get("sourcePath"), f"asset-{index}")
    mime_type = _clean_text(item.get("mime_type") or item.get("type"), "application/octet-stream")
    kind = "image" if mime_type.startswith("image/") else "audio" if mime_type.startswith("audio/") else "video"
    return {
        "id": _clean_text(item.get("id"), f"asset-{index}"),
        "name": name,
        "kind": _clean_text(item.get("kind"), kind),
        "mime_type": mime_type,
        "source": _clean_text(item.get("source") or item.get("sourcePath") or item.get("path"), name),
        "duration": _number(item.get("duration"), 5.0, 0.25),
    }


def _normalize_asset(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    return {
        "id": _clean_text(item.get("id"), f"asset-{index}"),
        "name": _clean_text(item.get("name"), f"Asset {index}"),
        "kind": _clean_text(item.get("kind"), "video"),
        "mime_type": _clean_text(item.get("mime_type"), "video/mp4"),
        "source": _clean_text(item.get("source"), f"asset-{index}"),
        "duration": _number(item.get("duration"), 5.0, 0.25),
    }


def _normalize_clip(item: Any, index: int, start: float) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    duration = _number(item.get("duration") or item.get("out"), 5.0, 0.25)
    clip_in = _number(item.get("in"), 0.0, 0.0)
    clip_out = _number(item.get("out"), clip_in + duration, clip_in + 0.25)
    duration = _number(clip_out - clip_in if "out" in item else duration, duration, 0.25)
    return {
        "id": _clean_text(item.get("id"), f"clip-{index}"),
        "name": _clean_text(item.get("name") or item.get("label"), f"Clip {index}"),
        "asset_id": _clean_text(item.get("asset_id"), f"asset-{index}"),
        "track": _clean_text(item.get("track"), "video"),
        "start": _number(item.get("start"), start, 0.0),
        "duration": duration,
        "in": clip_in,
        "out": _number(clip_in + duration, clip_in + duration, clip_in + 0.25),
        "color": _clean_text(item.get("color"), MOVIE_CLIP_COLORS[(index - 1) % len(MOVIE_CLIP_COLORS)]),
    }


def _normalize_caption(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    return {
        "id": _clean_text(item.get("id"), f"caption-{index}"),
        "text": _clean_text(item.get("text"), "Caption line"),
        "start": _number(item.get("start"), max(0.0, (index - 1) * 4.0), 0.0),
        "duration": _number(item.get("duration"), 3.5, 0.25),
    }


def _resequence_project(project: dict[str, Any]) -> dict[str, Any]:
    clips = []
    cursor = 0.0
    for index, clip in enumerate(project.get("clips") if isinstance(project.get("clips"), list) else [], start=1):
        normalized = _normalize_clip(clip, index, cursor)
        normalized["start"] = cursor
        cursor = round(cursor + normalized["duration"], 3)
        clips.append(normalized)
    project["clips"] = clips
    project["timeline"] = {
        "duration": cursor,
        "fps": int(_number(project.get("fps"), 30, 1)),
        "tracks": ["video", "audio", "captions"],
    }
    return project


def default_movie_project(text: str, attached_files: list[Any] | None = None, resource_id: str = "") -> dict[str, Any]:
    title = _first_title_line(text, "Untitled movie")
    attached_assets = [
        asset
        for index, item in enumerate(attached_files or [], start=1)
        if (asset := _asset_from_attached(item, index)) is not None
    ]
    assets = attached_assets or [
        {"id": "asset-1", "name": "Opening card", "kind": "video", "mime_type": "video/mp4", "source": "generated:opening-card", "duration": 4.0},
        {"id": "asset-2", "name": "Product demo", "kind": "video", "mime_type": "video/mp4", "source": "generated:product-demo", "duration": 6.0},
        {"id": "asset-3", "name": "End slate", "kind": "video", "mime_type": "video/mp4", "source": "generated:end-slate", "duration": 3.0},
    ]
    clips = [
        {"id": "clip-1", "name": title[:28] or "Intro", "asset_id": assets[0]["id"], "track": "video", "duration": min(assets[0]["duration"], 4.0), "color": "sky"},
        {"id": "clip-2", "name": "Demo", "asset_id": assets[min(1, len(assets) - 1)]["id"], "track": "video", "duration": 6.0, "color": "violet"},
        {"id": "clip-3", "name": "Call to action", "asset_id": assets[min(2, len(assets) - 1)]["id"], "track": "video", "duration": 3.0, "color": "emerald"},
    ]
    project = {
        "project_id": resource_id or "movie:scratch",
        "title": title,
        "brief": text,
        "format": "16:9 / H.264",
        "resolution": "1920x1080",
        "fps": 30,
        "assets": assets,
        "clips": clips,
        "captions": [
            {"id": "caption-1", "text": title, "start": 0.4, "duration": 3.2},
            {"id": "caption-2", "text": "Show the product benefit clearly.", "start": 5.0, "duration": 3.6},
        ],
        "audio": {"music": "local-placeholder", "voice_gain": 0.82, "ducking": True},
        "render": {
            "engine": "ffmpeg" if shutil.which("ffmpeg") else "unavailable",
            "enabled": bool(shutil.which("ffmpeg")),
            "status": "ready" if shutil.which("ffmpeg") else "disabled",
        },
        "operations": list(MOVIE_OPERATIONS),
    }
    return _resequence_project(project)


def normalize_movie_project(raw: Any, fallback_text: str = "", resource_id: str = "") -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_movie_project(fallback_text, resource_id=resource_id)
    base = default_movie_project(_clean_text(raw.get("brief"), fallback_text), resource_id=resource_id)
    project = deepcopy(raw)
    project.setdefault("project_id", resource_id or base["project_id"])
    project.setdefault("title", _first_title_line(project.get("brief") or fallback_text, base["title"]))
    project.setdefault("brief", fallback_text)
    project.setdefault("format", base["format"])
    project.setdefault("resolution", base["resolution"])
    project.setdefault("fps", base["fps"])
    project["assets"] = [
        _normalize_asset(asset, index)
        for index, asset in enumerate(project.get("assets") if isinstance(project.get("assets"), list) else base["assets"], start=1)
    ]
    project["clips"] = [
        _normalize_clip(clip, index, 0.0)
        for index, clip in enumerate(project.get("clips") if isinstance(project.get("clips"), list) else base["clips"], start=1)
    ]
    project["captions"] = [
        _normalize_caption(caption, index)
        for index, caption in enumerate(project.get("captions") if isinstance(project.get("captions"), list) else base["captions"], start=1)
    ]
    project.setdefault("audio", base["audio"])
    project.setdefault("render", base["render"])
    project["operations"] = list(MOVIE_OPERATIONS)
    return _resequence_project(project)


def default_image_project(text: str, attached_files: list[Any] | None = None, resource_id: str = "") -> dict[str, Any]:
    assets = [
        asset
        for index, item in enumerate(attached_files or [], start=1)
        if (asset := _asset_from_attached(item, index)) is not None
    ]
    return {
        "project_id": resource_id or "image:scratch",
        "prompt": text,
        "mode": "compose",
        "canvas": {"width": 1024, "height": 1024, "background": "#111827"},
        "assets": assets,
        "variants": [
            {"id": "variant-1", "label": "Draft", "status": "editable"},
            {"id": "variant-2", "label": "Mask", "status": "ready"},
        ],
        "operations": ["image_generate", "image_mask", "image_crop", "image_export"],
    }


def open_surface(surface_id: str, args: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    config = SURFACES[surface_id]
    payload = dict(args or {})
    conversation_id = str(payload.get("conversation_id") or (context or {}).get("conversation_id") or "").strip()
    resource_id = str(payload.get("resource_id") or f"{surface_id}:{conversation_id or 'scratch'}").strip()
    attached_files = payload.get("attached_files") if isinstance(payload.get("attached_files"), list) else []
    initial_text = str(payload.get("text") or payload.get("prompt") or config["initial_text"])
    surface_payload: dict[str, Any] = {
        "initial_text": initial_text,
        "selection": payload.get("selection"),
        "attached_files": attached_files,
    }
    if surface_id == "movie":
        surface_payload["movie_project"] = normalize_movie_project(
            payload.get("movie_project") or payload.get("project"),
            initial_text,
            resource_id,
        )
        surface_payload["operations"] = list(MOVIE_OPERATIONS)
        surface_payload["tool_timeline"] = surface_payload["movie_project"]["timeline"]
    elif surface_id == "image":
        surface_payload["image_project"] = default_image_project(initial_text, attached_files, resource_id)
    descriptor = {
        "id": resource_id,
        "kind": config["kind"],
        "title": config["title"],
        "sourcePackId": PACK_ID,
        "renderer": config["renderer"],
        "conversationId": conversation_id,
        "resourceId": resource_id,
        "payload": surface_payload,
        "layoutMode": "split",
        "chatPlacement": "left",
    }
    return {
        "status": "ok",
        "data": {
            "surface": descriptor,
            "effects": [{"type": "surface.open", "surface": descriptor}],
            "message": f"{config['title']} surface opened.",
        },
    }


def _movie_project_from_args(args: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(args or {})
    text = _clean_text(payload.get("text") or payload.get("brief"), "Movie brief")
    resource_id = _clean_text(payload.get("resource_id") or payload.get("project_id"), "movie:scratch")
    return normalize_movie_project(payload.get("project") or payload.get("movie_project"), text, resource_id)


def _ok_operation(operation: str, project: dict[str, Any], **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "operation": operation,
        "project": project,
        "timeline": project.get("timeline"),
        "message": f"{operation} completed.",
    }
    data.update(extra)
    return {"status": "ok", "data": data}


def movie_import_media(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = _movie_project_from_args(payload)
    media = payload.get("media") if isinstance(payload.get("media"), dict) else {}
    next_index = len(project.get("assets", [])) + 1
    asset = _normalize_asset(
        {
            "id": media.get("id") if isinstance(media, dict) else None,
            "name": media.get("name") if isinstance(media, dict) else payload.get("name"),
            "kind": media.get("kind") if isinstance(media, dict) else payload.get("kind"),
            "mime_type": media.get("mime_type") if isinstance(media, dict) else payload.get("mime_type"),
            "source": media.get("source") if isinstance(media, dict) else payload.get("source"),
            "duration": media.get("duration") if isinstance(media, dict) else payload.get("duration"),
        },
        next_index,
    )
    project["assets"].append(asset)
    project["clips"].append(
        _normalize_clip(
            {
                "id": f"clip-{len(project['clips']) + 1}",
                "name": asset["name"],
                "asset_id": asset["id"],
                "track": "audio" if asset["kind"] == "audio" else "video",
                "duration": asset["duration"],
                "color": MOVIE_CLIP_COLORS[len(project["clips"]) % len(MOVIE_CLIP_COLORS)],
            },
            len(project["clips"]) + 1,
            float(project.get("timeline", {}).get("duration") or 0),
        )
    )
    return _ok_operation("movie_import_media", _resequence_project(project), asset=asset)


def movie_edit_timeline(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = _movie_project_from_args(payload)
    order = payload.get("order") if isinstance(payload.get("order"), list) else []
    if order:
        rank = {str(clip_id): index for index, clip_id in enumerate(order)}
        project["clips"] = sorted(
            project["clips"],
            key=lambda clip: rank.get(str(clip.get("id")), len(rank) + project["clips"].index(clip)),
        )
    replacement_clips = payload.get("clips")
    if isinstance(replacement_clips, list):
        project["clips"] = [_normalize_clip(clip, index, 0.0) for index, clip in enumerate(replacement_clips, start=1)]
    return _ok_operation("movie_edit_timeline", _resequence_project(project))


def movie_trim_clip(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = _movie_project_from_args(payload)
    clip_id = _clean_text(payload.get("clip_id"), str(project["clips"][0]["id"]) if project.get("clips") else "")
    for clip in project.get("clips", []):
        if str(clip.get("id")) != clip_id:
            continue
        clip["in"] = _number(payload.get("in"), clip.get("in", 0.0), 0.0)
        if "out" in payload:
            clip["out"] = _number(payload.get("out"), clip.get("out", clip["in"] + clip["duration"]), clip["in"] + 0.25)
            clip["duration"] = _number(float(clip["out"]) - float(clip["in"]), clip["duration"], 0.25)
        elif "duration" in payload:
            clip["duration"] = _number(payload.get("duration"), clip.get("duration", 1.0), 0.25)
            clip["out"] = _number(float(clip["in"]) + float(clip["duration"]), float(clip["in"]) + float(clip["duration"]), float(clip["in"]) + 0.25)
        return _ok_operation("movie_trim_clip", _resequence_project(project), clip=clip)
    return {"status": "error", "error": {"code": "CLIP_NOT_FOUND", "message": f"clip not found: {clip_id}"}}


def movie_split_clip(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = _movie_project_from_args(payload)
    clip_id = _clean_text(payload.get("clip_id"), str(project["clips"][0]["id"]) if project.get("clips") else "")
    for index, clip in enumerate(project.get("clips", [])):
        if str(clip.get("id")) != clip_id:
            continue
        original_duration = _number(clip.get("duration"), 0.0, 0.0)
        if original_duration <= 0.5:
            return {
                "status": "error",
                "error": {
                    "code": "CLIP_TOO_SHORT",
                    "message": f"clip is too short to split: {clip_id}",
                },
            }
        split_at = _number(payload.get("split_at"), original_duration / 2.0)
        if split_at <= 0 or split_at >= original_duration or split_at < 0.25 or original_duration - split_at < 0.25:
            return {
                "status": "error",
                "error": {
                    "code": "INVALID_SPLIT_AT",
                    "message": "split_at must leave at least 0.25 seconds on both sides.",
                },
            }
        split_at = round(split_at, 3)
        second_duration = round(original_duration - split_at, 3)
        second = deepcopy(clip)
        clip["duration"] = split_at
        clip["out"] = _number(float(clip["in"]) + split_at, float(clip["in"]) + split_at, float(clip["in"]) + 0.25)
        second["id"] = _clean_text(payload.get("new_clip_id"), f"{clip_id}-split")
        second["name"] = f"{clip.get('name', 'Clip')} B"
        second["in"] = clip["out"]
        second["duration"] = second_duration
        second["out"] = _number(float(second["in"]) + float(second["duration"]), float(second["in"]) + float(second["duration"]), float(second["in"]) + 0.25)
        project["clips"].insert(index + 1, second)
        return _ok_operation("movie_split_clip", _resequence_project(project), clip=clip, new_clip=second)
    return {"status": "error", "error": {"code": "CLIP_NOT_FOUND", "message": f"clip not found: {clip_id}"}}


def movie_update_captions(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = _movie_project_from_args(payload)
    captions = payload.get("captions")
    if isinstance(captions, list):
        project["captions"] = [_normalize_caption(item, index) for index, item in enumerate(captions, start=1)]
    else:
        caption_id = _clean_text(payload.get("caption_id"), "")
        existing_index = next(
            (
                index
                for index, item in enumerate(project.get("captions", []))
                if caption_id and str(item.get("id")) == caption_id
            ),
            -1,
        )
        if existing_index >= 0:
            existing = project["captions"][existing_index]
            project["captions"][existing_index] = _normalize_caption(
                {
                    **existing,
                    "id": existing.get("id"),
                    "text": payload.get("text") or payload.get("caption_text") or existing.get("text"),
                    "start": payload.get("start") if "start" in payload else existing.get("start"),
                    "duration": payload.get("duration") if "duration" in payload else existing.get("duration"),
                },
                existing_index + 1,
            )
            return _ok_operation(
                "movie_update_captions",
                _resequence_project(project),
                captions=project.get("captions", []),
            )
        caption = _normalize_caption(
            {
                "id": caption_id or f"caption-{len(project.get('captions', [])) + 1}",
                "text": payload.get("text") or payload.get("caption_text") or project.get("title"),
                "start": payload.get("start"),
                "duration": payload.get("duration"),
            },
            len(project.get("captions", [])) + 1,
        )
        project.setdefault("captions", []).append(caption)
    return _ok_operation("movie_update_captions", _resequence_project(project), captions=project.get("captions", []))


def movie_save_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    project = _movie_project_from_args(args)
    saved_at = int(time.time() * 1000)
    project["saved_at"] = saved_at
    return _ok_operation(
        "movie_save_project",
        project,
        saved_at=saved_at,
        project_json=json.dumps(project, ensure_ascii=False, sort_keys=True),
    )


def movie_export_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    project = _movie_project_from_args(args)
    lines = [
        f"{clip['start']:06.2f} {clip['duration']:05.2f} {clip['track']} {clip['name']}"
        for clip in project.get("clips", [])
    ]
    export = {
        "filename": f"{project.get('project_id', 'movie').replace(':', '-')}.json",
        "project_json": json.dumps(project, ensure_ascii=False, sort_keys=True),
        "timeline_edl": "\n".join(lines),
        "captions": list(project.get("captions", [])),
    }
    return _ok_operation("movie_export_project", project, export=export)


def movie_render_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    project = _movie_project_from_args(args)
    ffmpeg_available = bool(shutil.which("ffmpeg"))
    render = {
        "status": "ready" if ffmpeg_available else "disabled",
        "enabled": ffmpeg_available,
        "engine": "ffmpeg" if ffmpeg_available else "unavailable",
        "output_name": f"{project.get('project_id', 'movie').replace(':', '-')}.mp4",
        "message": "ffmpeg render is available." if ffmpeg_available else "ffmpeg was not found; project export remains available.",
    }
    project["render"] = render
    return _ok_operation("movie_render_project", project, render=render)
