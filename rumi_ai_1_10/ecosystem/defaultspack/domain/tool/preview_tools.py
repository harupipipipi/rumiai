from __future__ import annotations

import re
from typing import Any

from ._agent_os_common import PNG_1X1, err, now_slug, ok, read_text_file, write_bytes_file, workspace


def html_preview(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        html_path = ws.resolve(path, must_exist=True)
        text = read_text_file(html_path)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else html_path.name
        screenshot = ws.resolve(f"previews/{html_path.stem}-{now_slug()}.png")
        write_bytes_file(screenshot, PNG_1X1)
        return ok(
            {
                "html_path": ws.relative(html_path),
                "screenshot_path": ws.relative(screenshot),
                "preview_url": "artifact://" + ws.relative(html_path),
                "title": title,
                "viewport": arguments.get("viewport") or {"width": 1280, "height": 720},
                "full_page": bool(arguments.get("full_page", True)),
                "fallback": "metadata_png",
            }
        )
    except Exception as exc:
        return err(str(exc), "HTML_PREVIEW_FAILED")


def artifact_preview(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        target = ws.resolve(path, must_exist=True, allow_root=True)
        if target.is_dir():
            entries = [item.name for item in sorted(target.iterdir())[:50]]
            return ok({"path": ws.relative(target) if target != ws.root else ".", "kind": "directory", "entries": entries})
        suffix = target.suffix.lower()
        if suffix in {".html", ".htm"}:
            return html_preview({"path": ws.relative(target), **arguments}, context)
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
            return ok({"path": ws.relative(target), "kind": "image", "size": target.stat().st_size})
        if suffix == ".pdf":
            return pdf_preview({"path": ws.relative(target), **arguments}, context)
        content = read_text_file(target, max_bytes=512_000)
        return ok({"path": ws.relative(target), "kind": "text", "content": content[:40_000], "truncated": len(content) > 40_000})
    except Exception as exc:
        return err(str(exc), "ARTIFACT_PREVIEW_FAILED")


def image_render(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    output_path = str(arguments.get("output_path") or f"renders/image-{now_slug()}.png")
    text = str(arguments.get("text") or arguments.get("prompt") or "Rumi artifact render")
    width = int((arguments.get("viewport") or {}).get("width") or arguments.get("width") or 1024)
    height = int((arguments.get("viewport") or {}).get("height") or arguments.get("height") or 640)
    try:
        ws = workspace(context)
        output = ws.resolve(output_path)
        try:
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (max(width, 1), max(height, 1)), color=(245, 247, 250))
            draw = ImageDraw.Draw(image)
            draw.text((32, 32), text[:500], fill=(22, 26, 31))
            output.parent.mkdir(parents=True, exist_ok=True)
            image.save(output)
        except Exception:
            write_bytes_file(output, PNG_1X1)
        return ok(
            {
                "path": ws.relative(output),
                "workspace_path": ws.workspace_relative(output),
                "width": width,
                "height": height,
            }
        )
    except Exception as exc:
        return err(str(exc), "IMAGE_RENDER_FAILED")


def pdf_preview(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        pdf_path = ws.resolve(path, must_exist=True)
        output = ws.resolve(f"previews/{pdf_path.stem}-{now_slug()}.png")
        write_bytes_file(output, PNG_1X1)
        return ok({"pdf_path": ws.relative(pdf_path), "screenshot_path": ws.relative(output), "fallback": "metadata_png"})
    except Exception as exc:
        return err(str(exc), "PDF_PREVIEW_FAILED")
