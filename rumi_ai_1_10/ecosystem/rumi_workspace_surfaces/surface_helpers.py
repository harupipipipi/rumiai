from __future__ import annotations

import json
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
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
        "initial_text": "",
    },
    "slide": {
        "title": "Slide",
        "kind": "slide",
        "renderer": "rumi_workspace_surfaces.slide",
        "initial_text": "",
    },
    "movie": {
        "title": "Movie",
        "kind": "movie",
        "renderer": "rumi_workspace_surfaces.movie",
        "initial_text": "",
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
SLIDE_ACCENTS = ["blue", "emerald", "amber", "rose", "violet", "cyan"]
_SAFE_COLOR = re.compile(r"^(?:#[0-9a-f]{3,8}|rgba?\([\d\s,.%]+\)|hsla?\([\d\s,.%]+\)|[a-z]+)$", re.I)
_SAFE_SVG_TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "clipPath", "mask", "use"}
_SAFE_SVG_ATTRS = {"xmlns", "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "d", "points", "fill", "fill-opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-opacity", "opacity", "transform", "font-size", "font-family", "font-weight", "text-anchor", "offset", "stop-color", "stop-opacity", "clip-path", "mask", "id", "href"}


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


def _percentage(value: Any, fallback: float) -> float:
    result = _number(value, fallback)
    if 0 < result <= 1:
        result *= 100
    return round(min(100.0, max(0.0, result)), 3)


def _safe_slide_style(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for source, target in (("color", "color"), ("background", "background"), ("backgroundColor", "background")):
        candidate = _clean_text(raw.get(source), "")
        if candidate and _SAFE_COLOR.fullmatch(candidate):
            result[target] = candidate
    for source, target, low, high in (("fontSize", "fontSize", 8, 72), ("font_size", "fontSize", 8, 72), ("fontWeight", "fontWeight", 100, 900), ("font_weight", "fontWeight", 100, 900), ("borderRadius", "borderRadius", 0, 64), ("border_radius", "borderRadius", 0, 64)):
        if source in raw:
            result[target] = min(high, _number(raw[source], low, low))
    align = _clean_text(raw.get("textAlign") or raw.get("text_align"), "")
    if align in {"left", "center", "right"}:
        result["textAlign"] = align
    fit = _clean_text(raw.get("objectFit") or raw.get("object_fit"), "")
    if fit in {"contain", "cover", "fill", "none", "scale-down"}:
        result["objectFit"] = fit
    return result


def _sanitized_svg_data_uri(value: Any) -> str:
    source = _clean_text(value, "")
    if source.lower().startswith("data:image/svg+xml"):
        try:
            source = urllib.parse.unquote(source.split(",", 1)[1])
        except (IndexError, ValueError):
            return ""
    if not source.lstrip().startswith("<svg"):
        return ""
    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        root = ET.fromstring(source)
    except ET.ParseError:
        return ""
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] not in _SAFE_SVG_TAGS:
                parent.remove(child)
    for node in root.iter():
        for attribute in list(node.attrib):
            name = attribute.rsplit("}", 1)[-1]
            content = node.attrib[attribute].strip()
            safe_url = not "url(" in content.lower() or bool(re.fullmatch(r"url\(#[A-Za-z0-9_.:-]+\)", content))
            if name not in _SAFE_SVG_ATTRS or name.startswith("on") or (name == "href" and not content.startswith("#")) or not safe_url:
                del node.attrib[attribute]
    sanitized = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return "data:image/svg+xml;charset=utf-8," + urllib.parse.quote(sanitized, safe="")


def _embedded_image_data(value: Any) -> tuple[str, str, str]:
    """Return allowlisted embedded image data, MIME type, and file extension."""
    svg_source = _sanitized_svg_data_uri(value)
    if svg_source:
        return svg_source, "image/svg+xml", "svg"
    source = _clean_text(value, "")
    match = re.fullmatch(
        r"data:image/(png|jpeg|gif|webp|avif);base64,([A-Za-z0-9+/]+={0,2})",
        source,
        re.I,
    )
    if not match:
        return "", "", ""
    subtype = match.group(1).lower()
    return source, f"image/{subtype}", "jpg" if subtype == "jpeg" else subtype


def _natural_text(text: Any) -> str:
    """Return user prose while excluding structured project JSON."""
    source = str(text or "").strip()
    if not source:
        return ""
    parsed = _json_object_from_text(source)
    if not parsed:
        return source
    return _clean_text(parsed.get("text") or parsed.get("prompt"), "")


def _asset_from_attached(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _clean_text(item.get("name") or item.get("path") or item.get("sourcePath"), f"asset-{index}")
    mime_type = _clean_text(item.get("mime_type") or item.get("type"), "application/octet-stream")
    kind = "image" if mime_type.startswith("image/") else "audio" if mime_type.startswith("audio/") else "video"
    normalized = deepcopy(item)
    normalized.update({
        "id": _clean_text(item.get("id") or item.get("asset_id"), f"asset-{index}"),
        "name": name,
        "kind": _clean_text(item.get("kind"), kind),
        "mime_type": mime_type,
        "source": _clean_text(
            item.get("source")
            or item.get("sourcePath")
            or item.get("path")
            or item.get("url")
            or item.get("data_uri")
            or item.get("data")
            or item.get("image_data"),
            name,
        ),
        "duration": _number(item.get("duration"), 5.0, 0.25),
    })
    return normalized


def _slide_asset_from_attached(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _clean_text(item.get("name") or item.get("path") or item.get("sourcePath"), f"asset-{index}")
    mime_type = _clean_text(item.get("mime_type") or item.get("type"), "application/octet-stream")
    if mime_type.startswith("image/"):
        kind = "image"
    elif mime_type.startswith("video/"):
        kind = "video"
    elif mime_type.startswith("audio/"):
        kind = "audio"
    elif mime_type in {"application/pdf", "text/markdown", "text/plain"}:
        kind = "document"
    else:
        kind = _clean_text(item.get("kind"), "file")
    normalized = deepcopy(item)
    normalized.update({
        "id": _clean_text(item.get("id") or item.get("asset_id"), f"asset-{index}"),
        "name": name,
        "kind": _clean_text(item.get("kind"), kind),
        "mime_type": mime_type,
        "source": _clean_text(
            item.get("source")
            or item.get("sourcePath")
            or item.get("path")
            or item.get("url")
            or item.get("data_uri")
            or item.get("data")
            or item.get("image_data"),
            name,
        ),
    })
    return normalized


def _normalize_slide_asset(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    normalized = deepcopy(item)
    raw_kind = _clean_text(item.get("kind") or item.get("type"), "image")
    kind = raw_kind.split("/", 1)[0] if "/" in raw_kind else raw_kind
    default_mime = "image/png" if kind == "image" else "application/octet-stream"
    normalized.update(
        {
            "id": _clean_text(item.get("id") or item.get("asset_id"), f"asset-{index}"),
            "name": _clean_text(item.get("name") or item.get("id") or item.get("asset_id"), f"Asset {index}"),
            "kind": kind,
            "mime_type": _clean_text(item.get("mime_type"), default_mime),
            "source": _clean_text(
                item.get("source")
                or item.get("path")
                or item.get("url")
                or item.get("data_uri")
                or item.get("data")
                or item.get("image_data"),
                "",
            ),
        }
    )
    return normalized


def _normalize_asset(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    raw_kind = _clean_text(item.get("kind") or item.get("type"), "video")
    kind = raw_kind.split("/", 1)[0] if "/" in raw_kind else raw_kind
    default_mime = "image/png" if kind == "image" else "audio/mpeg" if kind == "audio" else "video/mp4"
    placement = item.get("placement") if isinstance(item.get("placement"), dict) else {}
    placement_duration = None
    if placement:
        placement_duration = _number(placement.get("end"), 0.0, 0.0) - _number(placement.get("start"), 0.0, 0.0)
    normalized = deepcopy(item)
    normalized.update(
        {
            "id": _clean_text(item.get("id") or item.get("asset_id"), f"asset-{index}"),
            "name": _clean_text(item.get("name") or item.get("id") or item.get("asset_id"), f"Asset {index}"),
            "kind": kind,
            "mime_type": _clean_text(item.get("mime_type"), default_mime),
            "source": _clean_text(
                item.get("source")
                or item.get("path")
                or item.get("url")
                or item.get("data_uri")
                or item.get("data")
                or item.get("image_data"),
                "",
            ),
            "duration": _number(item.get("duration"), placement_duration or 5.0, 0.25),
        }
    )
    return normalized


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    if not source:
        return None
    if source.startswith("```"):
        lines = source.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        source = "\n".join(lines).strip()
    candidates = [source]
    if "{" in source and "}" in source:
        candidates.append(source[source.find("{"):source.rfind("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _slide_project_payload_from_text(text: str) -> dict[str, Any] | None:
    parsed = _json_object_from_text(text)
    if not parsed:
        return None
    raw = parsed.get("slide_project") or parsed.get("deck") or parsed.get("project") or parsed
    if not isinstance(raw, dict) or not any(field in raw for field in ("slides", "assets", "title", "brief")):
        return None
    project = deepcopy(raw)
    project.setdefault("brief", parsed.get("text") or parsed.get("prompt") or "")
    return project


def _movie_project_payload_from_text(text: str) -> dict[str, Any] | None:
    parsed = _json_object_from_text(text)
    if not parsed:
        return None
    raw = parsed.get("movie_project") or parsed.get("project") or parsed
    if not isinstance(raw, dict) or not any(
        field in raw for field in ("clips", "assets", "captions", "timeline", "title", "brief")
    ):
        return None
    project = deepcopy(raw)
    project.setdefault("brief", parsed.get("text") or parsed.get("prompt") or "")
    if parsed.get("resource_id") and "project_id" not in project:
        project["project_id"] = parsed.get("resource_id")
    return project


def _image_project_payload_from_text(text: str) -> dict[str, Any] | None:
    parsed = _json_object_from_text(text)
    if not parsed:
        return None
    raw = parsed.get("image_project") or parsed.get("project") or parsed
    if not isinstance(raw, dict) or not any(
        field in raw for field in ("assets", "variants", "canvas", "prompt", "title")
    ):
        return None
    project = deepcopy(raw)
    project.setdefault("prompt", parsed.get("text") or parsed.get("prompt") or "")
    return project


def _slug(value: str, fallback: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug[:48] or fallback


def _line_items(text: str) -> list[str]:
    items = []
    for line in str(text or "").splitlines():
        cleaned = line.strip().lstrip("#").strip()
        while cleaned.startswith(("- ", "* ")):
            cleaned = cleaned[2:].strip()
        if cleaned:
            items.append(cleaned)
    return items


def _derive_slide_specs(text: str) -> list[dict[str, Any]]:
    lines = str(text or "").splitlines()
    deck_title = _first_title_line(text, "Untitled deck")
    slides: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        heading = stripped.lstrip("#").strip() if stripped.startswith("#") else ""
        lower_heading = heading.lower()
        is_slide_heading = bool(heading) and (
            lower_heading.startswith("slide ")
            or lower_heading.startswith("section ")
            or stripped.startswith("##")
        )
        if is_slide_heading:
            if current:
                slides.append(current)
            current = {"title": heading, "bullets": [], "notes": ""}
            continue
        if current is None:
            if stripped.startswith("#"):
                continue
            current = {"title": deck_title, "bullets": [], "notes": ""}
        bullet = stripped.lstrip("-*0123456789. ").strip()
        if bullet:
            current.setdefault("bullets", []).append(bullet)
    if current:
        slides.append(current)

    compact = _line_items(text)
    if not slides and compact:
        slides = [{"title": deck_title, "bullets": compact[1:4] or compact[:3], "notes": ""}]
    return slides[:12]


def _normalize_slide(item: Any, index: int, attached_asset_ids: list[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    raw_bullets = item.get("bullets") or item.get("points") or item.get("content")
    if isinstance(raw_bullets, str):
        bullets = _line_items(raw_bullets)
    elif isinstance(raw_bullets, list):
        bullets = [_clean_text(bullet) for bullet in raw_bullets if _clean_text(bullet)]
    else:
        bullets = []
    asset_ids = item.get("asset_ids") or item.get("assets")
    normalized_asset_ids = [
        _clean_text(asset.get("id") if isinstance(asset, dict) else asset)
        for asset in (asset_ids if isinstance(asset_ids, list) else [])
        if _clean_text(asset.get("id") if isinstance(asset, dict) else asset)
    ]
    if not normalized_asset_ids and index <= len(attached_asset_ids):
        normalized_asset_ids = [attached_asset_ids[index - 1]]
    elements = []
    raw_layout = item.get("layout") if isinstance(item.get("layout"), dict) else {}
    raw_elements = item.get("elements") if isinstance(item.get("elements"), list) else raw_layout.get("elements", [])
    for element_index, element in enumerate(raw_elements, start=1):
        if not isinstance(element, dict):
            continue
        normalized_element = {
            "id": _clean_text(element.get("id"), f"element-{element_index}"),
            "type": _clean_text(element.get("type") or element.get("kind"), "text").lower(),
            "text": _clean_text(element.get("text") or element.get("content") or element.get("label"), ""),
            "x": _percentage(element.get("x", element.get("left")), 0),
            "y": _percentage(element.get("y", element.get("top")), 0),
            "width": _percentage(element.get("width", element.get("w")), 100),
            "height": _percentage(element.get("height", element.get("h")), 100),
            "style": _safe_slide_style(element.get("style")),
        }
        asset_id = element.get("asset_id") or element.get("assetId")
        if asset_id:
            normalized_element["asset_id"] = _clean_text(asset_id)
        elements.append(normalized_element)
    normalized = deepcopy(item)
    normalized.update(
        {
            "id": _clean_text(item.get("id"), f"slide-{index}"),
            "title": _clean_text(item.get("title") or item.get("heading"), f"Slide {index}"),
            "subtitle": _clean_text(item.get("subtitle") or item.get("summary"), ""),
            "layout": _clean_text(
                raw_layout.get("name") if raw_layout else item.get("layout"),
                "title-and-bullets" if bullets else "title",
            ),
            "bullets": bullets[:8],
            "notes": _clean_text(item.get("notes") or item.get("speaker_notes"), ""),
            "accent": _clean_text(item.get("accent"), SLIDE_ACCENTS[(index - 1) % len(SLIDE_ACCENTS)]),
            "asset_ids": normalized_asset_ids,
            "elements": elements,
        }
    )
    return normalized


def _normalize_clip(item: Any, index: int, start: float) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    clip_start = _number(item.get("start"), start, 0.0)
    end = _number(item.get("end"), clip_start, clip_start) if "end" in item else None
    duration_fallback = max(0.25, round(float(end) - clip_start, 3)) if end is not None else 5.0
    raw_out = item.get("out") if "out" in item else item.get("out_point")
    duration = _number(item.get("duration") or raw_out, duration_fallback, 0.25)
    clip_in = _number(item.get("in") if "in" in item else item.get("in_point"), 0.0, 0.0)
    clip_out = _number(raw_out, clip_in + duration, clip_in + 0.25)
    duration = _number(
        clip_out - clip_in if "out" in item or "out_point" in item else duration,
        duration,
        0.25,
    )
    normalized = deepcopy(item)
    normalized.update(
        {
        "id": _clean_text(item.get("id"), f"clip-{index}"),
        "name": _clean_text(item.get("name") or item.get("label") or item.get("source"), f"Clip {index}"),
        "asset_id": _clean_text(
            item.get("asset_id") or item.get("assetId") or item.get("source"),
            f"asset-{index}",
        ),
        "track": _clean_text(item.get("track"), "video"),
        "start": clip_start,
        "duration": duration,
        "in": clip_in,
        "out": _number(clip_in + duration, clip_in + duration, clip_in + 0.25),
        "color": _clean_text(item.get("color"), MOVIE_CLIP_COLORS[(index - 1) % len(MOVIE_CLIP_COLORS)]),
        }
    )
    normalized.setdefault("source", item.get("source"))
    normalized["end"] = _number(float(normalized["start"]) + duration, float(normalized["start"]) + duration, float(normalized["start"]) + 0.25)
    return normalized


def _normalize_caption(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    start = _number(item.get("start"), max(0.0, (index - 1) * 4.0), 0.0)
    end = _number(item.get("end"), start, start) if "end" in item else None
    duration_fallback = max(0.25, round(float(end) - start, 3)) if end is not None else 3.5
    duration = _number(item.get("duration"), duration_fallback, 0.25)
    normalized = deepcopy(item)
    normalized.update(
        {
        "id": _clean_text(item.get("id"), f"caption-{index}"),
        "text": _clean_text(item.get("text") or item.get("caption") or item.get("content"), ""),
        "start": start,
        "duration": duration,
        }
    )
    normalized["end"] = _number(float(start) + duration, float(start) + duration, float(start) + 0.25)
    return normalized


def _resequence_project(
    project: dict[str, Any],
    *,
    preserve_starts: bool = False,
    preserve_timeline: bool = False,
) -> dict[str, Any]:
    clips = []
    cursor = 0.0
    for index, clip in enumerate(project.get("clips") if isinstance(project.get("clips"), list) else [], start=1):
        normalized = _normalize_clip(clip, index, cursor)
        if not preserve_starts or not isinstance(clip, dict) or "start" not in clip:
            normalized["start"] = cursor
        normalized["end"] = _number(
            float(normalized["start"]) + float(normalized["duration"]),
            float(normalized["start"]) + float(normalized["duration"]),
            float(normalized["start"]) + 0.25,
        )
        cursor = round(max(cursor, float(normalized["end"])), 3)
        clips.append(normalized)
    for caption in project.get("captions") if isinstance(project.get("captions"), list) else []:
        if isinstance(caption, dict):
            cursor = max(
                cursor,
                _number(caption.get("start"), 0.0, 0.0)
                + _number(caption.get("duration"), 0.0, 0.0),
            )
    project["clips"] = clips
    raw_timeline = project.get("timeline") if isinstance(project.get("timeline"), dict) else {}
    timeline = deepcopy(raw_timeline)
    if preserve_timeline:
        timeline.setdefault("duration", cursor)
    else:
        timeline["duration"] = cursor
    timeline.setdefault("fps", int(_number(project.get("fps"), 30, 1)))
    if not preserve_timeline or "tracks" not in timeline:
        tracks = list(dict.fromkeys(_clean_text(clip.get("track"), "video") for clip in clips))
        if project.get("captions"):
            tracks.append("captions")
        timeline["tracks"] = tracks
    project["timeline"] = timeline
    return project


def default_movie_project(text: str, attached_files: list[Any] | None = None, resource_id: str = "") -> dict[str, Any]:
    clean_text = _natural_text(text)
    title = _first_title_line(clean_text, "Untitled movie")
    attached_assets = [
        asset
        for index, item in enumerate(attached_files or [], start=1)
        if (asset := _asset_from_attached(item, index)) is not None
    ]
    assets = attached_assets
    clips = [
        {
            "id": f"clip-{index}",
            "name": asset["name"],
            "asset_id": asset["id"],
            "track": "audio" if asset.get("kind") == "audio" else "video",
            "duration": asset["duration"],
            "color": MOVIE_CLIP_COLORS[(index - 1) % len(MOVIE_CLIP_COLORS)],
        }
        for index, asset in enumerate(assets, start=1)
    ]
    project = {
        "project_id": resource_id or "movie:scratch",
        "title": title,
        "brief": clean_text,
        "format": "16:9 / H.264",
        "resolution": "1920x1080",
        "fps": 30,
        "assets": assets,
        "clips": clips,
        "captions": [],
        "audio": {"voice_gain": 0.82, "ducking": True},
        "render": {
            "engine": "unavailable",
            "enabled": False,
            "status": "disabled",
            "message": "No safe movie render route is configured.",
        },
        "operations": list(MOVIE_OPERATIONS),
    }
    return _resequence_project(project)


def normalize_movie_project(
    raw: Any,
    fallback_text: str = "",
    resource_id: str = "",
    attached_files: list[Any] | None = None,
) -> dict[str, Any]:
    clean_fallback = _natural_text(fallback_text)
    if not isinstance(raw, dict):
        raw = _movie_project_payload_from_text(fallback_text) or {}
    if not raw:
        return default_movie_project(clean_fallback, attached_files=attached_files, resource_id=resource_id)
    base = default_movie_project(
        _clean_text(raw.get("brief"), clean_fallback),
        attached_files=attached_files,
        resource_id=resource_id,
    )
    project = deepcopy(raw)
    project.setdefault("project_id", resource_id or base["project_id"])
    project.setdefault("title", _first_title_line(project.get("brief") or clean_fallback, base["title"]))
    project.setdefault("brief", clean_fallback)
    project.setdefault("format", base["format"])
    project.setdefault("resolution", base["resolution"])
    timeline_fps = project.get("timeline", {}).get("fps") if isinstance(project.get("timeline"), dict) else None
    project.setdefault("fps", timeline_fps or base["fps"])
    raw_assets = project.get("assets") if isinstance(project.get("assets"), list) else base["assets"]
    project["assets"] = [
        _normalize_asset(asset, index)
        for index, asset in enumerate(raw_assets, start=1)
    ]
    raw_clips = project.get("clips") if isinstance(project.get("clips"), list) else base["clips"]
    if not isinstance(project.get("clips"), list) and isinstance(project.get("timeline"), dict):
        timeline_clips = project["timeline"].get("clips")
        if isinstance(timeline_clips, list):
            raw_clips = timeline_clips
    project["clips"] = [
        _normalize_clip(clip, index, 0.0)
        for index, clip in enumerate(raw_clips, start=1)
    ]
    raw_captions = project.get("captions") if isinstance(project.get("captions"), list) else base["captions"]
    project["captions"] = [
        _normalize_caption(caption, index)
        for index, caption in enumerate(raw_captions, start=1)
    ]
    project.setdefault("audio", base["audio"])
    project["render"] = deepcopy(base["render"])
    project["operations"] = list(MOVIE_OPERATIONS)
    return _resequence_project(project, preserve_starts=True, preserve_timeline=True)


def default_image_project(text: str, attached_files: list[Any] | None = None, resource_id: str = "") -> dict[str, Any]:
    assets = [
        asset
        for index, item in enumerate(attached_files or [], start=1)
        if (asset := _asset_from_attached(item, index)) is not None
    ]
    return {
        "project_id": resource_id or "image:scratch",
        "prompt": _natural_text(text),
        "mode": "compose",
        "canvas": {"width": 1024, "height": 1024, "background": "#111827"},
        "assets": assets,
        "variants": [],
        "operations": ["image_export"],
    }


def normalize_image_project(
    raw: Any,
    fallback_text: str = "",
    resource_id: str = "",
    attached_files: list[Any] | None = None,
) -> dict[str, Any]:
    clean_fallback = _natural_text(fallback_text)
    if not isinstance(raw, dict):
        raw = _image_project_payload_from_text(fallback_text) or {}
    base = default_image_project(clean_fallback, attached_files, resource_id)
    if not raw:
        return base
    project = deepcopy(raw)
    project.setdefault("project_id", resource_id or base["project_id"])
    project.setdefault("prompt", clean_fallback)
    project.setdefault("mode", base["mode"])
    project.setdefault("canvas", base["canvas"])
    raw_assets = project.get("assets") if isinstance(project.get("assets"), list) else base["assets"]
    project["assets"] = [
        _normalize_asset(asset, index)
        for index, asset in enumerate(raw_assets, start=1)
    ]
    project.setdefault("variants", [])
    project["operations"] = list(base["operations"])
    return project


def default_slide_project(text: str, attached_files: list[Any] | None = None, resource_id: str = "") -> dict[str, Any]:
    clean_text = _natural_text(text)
    title = _first_title_line(clean_text, "Untitled deck")
    assets = [
        asset
        for index, item in enumerate(attached_files or [], start=1)
        if (asset := _slide_asset_from_attached(item, index)) is not None
    ]
    asset_ids = [asset["id"] for asset in assets]
    slides = [
        _normalize_slide(slide, index, asset_ids)
        for index, slide in enumerate(_derive_slide_specs(clean_text), start=1)
    ]
    return {
        "project_id": resource_id or "slide:scratch",
        "title": title,
        "brief": clean_text,
        "theme": {"name": "Rumi clean", "ratio": "16:9", "background": "#f8fafc", "accent": "#3b82f6"},
        "slides": slides,
        "assets": assets,
        "status_cards": [
            {"label": "Slides", "value": str(len(slides)), "status": "editable"},
            {"label": "Assets", "value": str(len(assets)), "status": "linked" if assets else "none"},
            {"label": "Export", "value": "pptx/json", "status": "ready"},
        ],
        "export": {
            "format": "pptx",
            "filename": f"{_slug(resource_id or title, 'deck')}.pptx",
            "status": "ready",
        },
        "operations": ["slide_save_project", "slide_export_deck"],
    }


def normalize_slide_project(
    raw: Any,
    fallback_text: str = "",
    resource_id: str = "",
    attached_files: list[Any] | None = None,
) -> dict[str, Any]:
    clean_fallback = _natural_text(fallback_text)
    if not isinstance(raw, dict):
        raw = _slide_project_payload_from_text(fallback_text) or {}
    base = default_slide_project(clean_fallback, attached_files=attached_files, resource_id=resource_id)
    if not raw:
        return base

    project = deepcopy(raw)
    project.setdefault("project_id", resource_id or base["project_id"])
    project.setdefault("title", _first_title_line(project.get("brief") or clean_fallback, base["title"]))
    project.setdefault("brief", clean_fallback)
    project.setdefault("theme", base["theme"])
    raw_assets = project.get("assets") if isinstance(project.get("assets"), list) else []
    assets = [_normalize_slide_asset(asset, index) for index, asset in enumerate(raw_assets, start=1)]
    attached_assets = [
        asset
        for index, item in enumerate(attached_files or [], start=len(assets) + 1)
        if (asset := _slide_asset_from_attached(item, index)) is not None
    ]
    existing_asset_ids = {asset["id"] for asset in assets}
    assets.extend(asset for asset in attached_assets if asset["id"] not in existing_asset_ids)
    asset_ids = [asset["id"] for asset in assets]

    slides = (
        project["slides"]
        if isinstance(project.get("slides"), list)
        else _derive_slide_specs(_clean_text(project.get("brief"), clean_fallback))
    )
    project["slides"] = [
        _normalize_slide(slide, index, asset_ids)
        for index, slide in enumerate(slides, start=1)
    ]
    project["assets"] = assets

    raw_status_cards = project.get("status_cards")
    project["status_cards"] = raw_status_cards if isinstance(raw_status_cards, list) else [
        {"label": "Slides", "value": str(len(project["slides"])), "status": "editable"},
        {"label": "Assets", "value": str(len(assets)), "status": "linked" if assets else "none"},
        {"label": "Export", "value": "pptx/json", "status": "ready"},
    ]
    raw_export = project.get("export") if isinstance(project.get("export"), dict) else {}
    project["export"] = {
        "format": _clean_text(raw_export.get("format"), "pptx"),
        "filename": _clean_text(
            raw_export.get("filename") or project.get("export_filename"),
            f"{_slug(project['project_id'], 'deck')}.pptx",
        ),
        "status": _clean_text(raw_export.get("status"), "ready"),
    }
    project["operations"] = ["slide_save_project", "slide_export_deck"]
    return project


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
            attached_files,
        )
        surface_payload["operations"] = list(MOVIE_OPERATIONS)
        surface_payload["tool_timeline"] = surface_payload["movie_project"]["timeline"]
    elif surface_id == "image":
        surface_payload["image_project"] = normalize_image_project(
            payload.get("image_project") or payload.get("project"),
            initial_text,
            resource_id,
            attached_files,
        )
    elif surface_id == "slide":
        surface_payload["slide_project"] = normalize_slide_project(
            payload.get("slide_project") or payload.get("deck") or payload.get("project"),
            initial_text,
            resource_id,
            attached_files,
        )
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
    text = _clean_text(payload.get("text") or payload.get("brief"), "")
    resource_id = _clean_text(payload.get("resource_id") or payload.get("project_id"), "movie:scratch")
    attached_files = payload.get("attached_files") if isinstance(payload.get("attached_files"), list) else None
    return normalize_movie_project(
        payload.get("project") or payload.get("movie_project"),
        text,
        resource_id,
        attached_files,
    )


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
        return _ok_operation(
            "movie_trim_clip",
            _resequence_project(project, preserve_starts=True),
            clip=clip,
        )
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
        second["start"] = _number(
            float(clip.get("start") or 0.0) + split_at,
            split_at,
            0.0,
        )
        second["duration"] = second_duration
        second["out"] = _number(float(second["in"]) + float(second["duration"]), float(second["in"]) + float(second["duration"]), float(second["in"]) + 0.25)
        project["clips"].insert(index + 1, second)
        return _ok_operation(
            "movie_split_clip",
            _resequence_project(project, preserve_starts=True),
            clip=clip,
            new_clip=second,
        )
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
                _resequence_project(project, preserve_starts=True),
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
    return _ok_operation(
        "movie_update_captions",
        _resequence_project(project, preserve_starts=True),
        captions=project.get("captions", []),
    )


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


def _artifact_name(value: Any, fallback: str, extension: str) -> str:
    stem = re.sub(
        r"[^a-zA-Z0-9._-]+", "-", _clean_text(value, fallback)
    ).strip(".-") or fallback
    safe_parts: list[str] = []
    for part in stem.split("-"):
        if part and not part.strip("."):
            if len(part) > 1 and safe_parts and safe_parts[-1].lower() != fallback.lower():
                safe_parts.pop()
            continue
        safe_parts.append(part)
    stem = "-".join(safe_parts) or fallback
    if stem.lower().endswith(f".{extension}"):
        stem = stem[: -(len(extension) + 1)]
    return f"{stem[:96]}.{extension}"


def image_export(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    source, mime_type, extension = _embedded_image_data(
        payload.get("svg")
        or payload.get("svg_data")
        or payload.get("source")
        or payload.get("data_uri")
    )
    if not source:
        return {"status": "error", "error": {"code": "IMAGE_EXPORT_DISABLED", "message": "Image export requires sanitized SVG or embedded image data."}}
    return {"status": "ok", "operation": "image_export", "export": {"filename": _artifact_name(payload.get("filename") or payload.get("name"), "image", extension), "source": source, "mime_type": mime_type}}


def slide_save_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = normalize_slide_project(payload.get("project") or payload.get("slide_project"), payload.get("text", ""), _clean_text(payload.get("resource_id"), ""), payload.get("attached_files"))
    saved_at = int(time.time() * 1000)
    project["saved_at"] = saved_at
    return {"status": "ok", "operation": "slide_save_project", "project": project, "saved_at": saved_at, "project_json": json.dumps(project, ensure_ascii=False, sort_keys=True)}


def _safe_slide_export_value(value: Any) -> Any:
    """Remove active or remotely loaded content from the embedded editable deck."""
    if isinstance(value, dict):
        return {key: _safe_slide_export_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_slide_export_value(item) for item in value]
    if not isinstance(value, str):
        return value
    source = value.strip()
    if source.lstrip().startswith("<svg") or source.lower().startswith("data:image/svg+xml"):
        return _sanitized_svg_data_uri(source)
    if re.match(r"^(?:https?:)?//", source, re.I) or source.lower().startswith("javascript:"):
        return ""
    return value


def slide_export_deck(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    payload = dict(args or {})
    project = normalize_slide_project(payload.get("project") or payload.get("slide_project"), payload.get("text", ""), _clean_text(payload.get("resource_id"), ""), payload.get("attached_files"))
    assets = {item.get("id"): item for item in project.get("assets", []) if isinstance(item, dict)}
    sections = []
    warnings = []
    for slide in project.get("slides", []):
        if not isinstance(slide, dict):
            continue
        body = []
        elements = slide.get("elements") if isinstance(slide.get("elements"), list) else []
        for element in elements:
            if not isinstance(element, dict):
                continue
            style_data = _safe_slide_style(element.get("style"))
            declarations = [f"left:{_percentage(element.get('x'), 0)}%", f"top:{_percentage(element.get('y'), 0)}%", f"width:{_percentage(element.get('width'), 100)}%", f"height:{_percentage(element.get('height'), 100)}%"]
            for key, css_key, suffix in (("color", "color", ""), ("background", "background", ""), ("fontSize", "font-size", "px"), ("fontWeight", "font-weight", ""), ("textAlign", "text-align", ""), ("objectFit", "object-fit", ""), ("borderRadius", "border-radius", "px")):
                if key in style_data:
                    declarations.append(f"{css_key}:{style_data[key]}{suffix}")
            style = html.escape(";".join(declarations), quote=True)
            kind = _clean_text(element.get("type"), "text").lower()
            text = html.escape(_clean_text(element.get("text"), ""))
            if kind in {"image", "asset"}:
                asset = assets.get(element.get("asset_id"), {})
                source, _, _ = _embedded_image_data(asset.get("source") if isinstance(asset, dict) else "")
                if source:
                    body.append(f'<img style="{style}" src="{html.escape(source, quote=True)}" alt="{html.escape(_clean_text(asset.get("name"), ""), quote=True)}">')
                else:
                    warnings.append(f"Asset {element.get('asset_id')} was omitted because it was not embedded image data.")
            elif kind == "bullets":
                items = [line.lstrip("-* ") for line in _clean_text(element.get("text"), "").splitlines() if line.strip()]
                body.append(f'<ul style="{style}">' + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>")
            else:
                body.append(f'<div class="element {html.escape(kind, quote=True)}" style="{style}">{text}</div>')
        if not elements:
            body.append(f'<h1>{html.escape(_clean_text(slide.get("title")))}</h1>')
        if not elements:
            subtitle = _clean_text(slide.get("subtitle"), "")
            if subtitle:
                body.append(f'<p class="subtitle">{html.escape(subtitle)}</p>')
            bullets = slide.get("bullets") if isinstance(slide.get("bullets"), list) else []
            if bullets:
                body.append("<ul>" + "".join(f"<li>{html.escape(_clean_text(item))}</li>" for item in bullets) + "</ul>")
        for asset_id in ([] if elements else slide.get("asset_ids") if isinstance(slide.get("asset_ids"), list) else []):
            asset = assets.get(asset_id, {})
            source = _clean_text(asset.get("source"), "") if isinstance(asset, dict) else ""
            sanitized_source, _, _ = _embedded_image_data(source)
            if sanitized_source:
                body.append(f'<img src="{html.escape(sanitized_source, quote=True)}" alt="{html.escape(_clean_text(asset.get("name"), ""), quote=True)}">')
            elif source:
                warnings.append(f"Asset {asset_id} was omitted because it was not embedded data.")
        sections.append('<section class="slide">' + "".join(body) + "</section>")
    export_project = _safe_slide_export_value(project)
    project_json = json.dumps(export_project, ensure_ascii=False).replace("</", "<\\/")
    deck_html = "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><style>html,body{margin:0;background:#111;font-family:system-ui,sans-serif}.slide{position:relative;box-sizing:border-box;width:100vw;aspect-ratio:16/9;overflow:hidden;padding:6%;background:#f8fafc;color:#18181b;page-break-after:always}.slide>.element,.slide>img,.slide>ul[style]{position:absolute;box-sizing:border-box;overflow:hidden}.slide h1{font-size:5vw;margin:0 0 2vw}.subtitle,.slide li{font-size:2.2vw;line-height:1.4}.slide img{object-fit:contain}</style></head><body>" + "".join(sections) + f'<script type="application/json" id="rumi-slide-project">{project_json}</script></body></html>'
    return {"status": "ok", "operation": "slide_export_deck", "project": project, "export": {"filename": _artifact_name(project.get("project_id") or project.get("title"), "deck", "html"), "mime_type": "text/html", "content": deck_html, "project_json": json.dumps(export_project, ensure_ascii=False, sort_keys=True), "warnings": warnings}}


def movie_export_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    project = _movie_project_from_args(args)
    lines = [
        f"{clip['start']:06.2f} {clip['duration']:05.2f} {clip['track']} {clip['name']}"
        for clip in project.get("clips", [])
    ]
    def timestamp(seconds: Any) -> str:
        milliseconds = max(0, int(round(_number(seconds, 0, 0) * 1000)))
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"
    cues = []
    for index, caption in enumerate(project.get("captions", []), start=1):
        if not isinstance(caption, dict):
            continue
        start = _number(caption.get("start"), 0, 0)
        end = start + _number(caption.get("duration"), 0.25, 0.25)
        cues.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{_clean_text(caption.get('text'))}")
    stem = _artifact_name(project.get("project_id"), "movie", "json")[:-5]
    export = {
        "filename": f"{stem}.json",
        "project_json": json.dumps(project, ensure_ascii=False, sort_keys=True),
        "timeline_edl": "\n".join(lines),
        "timeline_filename": f"{stem}-timeline.edl",
        "captions": list(project.get("captions", [])),
        "captions_vtt": "WEBVTT\n\n" + "\n\n".join(cues) + ("\n" if cues else ""),
        "captions_filename": f"{stem}-captions.vtt",
    }
    return _ok_operation("movie_export_project", project, export=export)


def movie_render_project(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    project = _movie_project_from_args(args)
    render = {
        "status": "disabled",
        "enabled": False,
        "engine": "unavailable",
        "output_name": f"{project.get('project_id', 'movie').replace(':', '-')}.mp4",
        "message": "No safe movie render route is configured; project, captions, and timeline export remain available.",
    }
    project["render"] = render
    return _ok_operation("movie_render_project", project, render=render)
