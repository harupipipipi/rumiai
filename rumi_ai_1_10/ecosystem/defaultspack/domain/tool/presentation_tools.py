from __future__ import annotations

from typing import Any

from ._agent_os_common import err, ok, read_text_file, write_minimal_pptx, workspace
from .export_tools import artifact_export


def _slides_from_markdown_text(text: str) -> list[dict[str, Any]]:
    slides: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            if current:
                slides.append(current)
            current = {"title": line.lstrip("#").strip() or "Slide", "bullets": []}
        elif line.startswith(("-", "*")):
            if current is None:
                current = {"title": "Slide", "bullets": []}
            current.setdefault("bullets", []).append(line.lstrip("-* ").strip())
    if current:
        slides.append(current)
    return slides or [{"title": "Slide", "bullets": []}]


def slides_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    output_path = str(arguments.get("output_path") or "slides/deck.pptx")
    slides = arguments.get("slides")
    if not isinstance(slides, list):
        slides = [{"title": str(arguments.get("title") or "Deck"), "bullets": []}]
    try:
        ws = workspace(context)
        output = ws.resolve(output_path)
        write_minimal_pptx(output, slides)
        return ok({"path": ws.relative(output), "slides": len(slides), "size": output.stat().st_size})
    except Exception as exc:
        return err(str(exc), "SLIDES_CREATE_FAILED")


def slides_update(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    slides = arguments.get("slides")
    if not path or not isinstance(slides, list):
        return err("'path' and 'slides' are required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        output = ws.resolve(path)
        write_minimal_pptx(output, slides)
        return ok({"path": ws.relative(output), "slides": len(slides), "size": output.stat().st_size})
    except Exception as exc:
        return err(str(exc), "SLIDES_UPDATE_FAILED")


def slides_from_markdown(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    markdown = str(arguments.get("markdown") or "")
    source_path = arguments.get("path")
    try:
        if source_path:
            ws = workspace(context)
            markdown = read_text_file(ws.resolve(str(source_path), must_exist=True))
        slides = _slides_from_markdown_text(markdown)
        return slides_create({**arguments, "slides": slides}, context)
    except Exception as exc:
        return err(str(exc), "SLIDES_FROM_MARKDOWN_FAILED")


def slides_export(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return artifact_export({**arguments, "format": str(arguments.get("format") or "pptx")}, context)
