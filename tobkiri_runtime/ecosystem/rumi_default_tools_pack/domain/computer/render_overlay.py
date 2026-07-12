"""Optional cursor overlay rendering for virtual pointer previews."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def render_cursor_overlay(
    source_path: str | Path,
    output_path: str | Path,
    pointer: dict[str, Any] | None = None,
    *,
    points: list[dict[str, Any]] | None = None,
    color: tuple[int, int, int, int] = (255, 0, 0, 255),
) -> dict[str, Any]:
    """Render a cursor/point overlay when Pillow is available.

    The module intentionally does not import Pillow at module import time. If
    Pillow is absent, callers receive a structured fallback instead of an
    ImportError.
    """

    source = Path(source_path)
    output = Path(output_path)
    markers = list(points or [])
    if pointer:
        markers.append(pointer)
    if not markers:
        return {"rendered": False, "reason": "no_points", "path": str(source)}

    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        copied = _copy_if_possible(source, output)
        return {
            "rendered": False,
            "reason": "pillow_unavailable",
            "path": str(output if copied else source),
        }

    try:
        with Image.open(source).convert("RGBA") as image:
            draw = ImageDraw.Draw(image)
            width, height = image.size
            radius = max(8, min(width, height) // 40)
            line_width = max(2, radius // 5)
            for marker in markers:
                point = _marker_point(marker, width, height)
                if point is None:
                    continue
                x, y = point
                draw.line((x - radius, y, x + radius, y), fill=color, width=line_width)
                draw.line((x, y - radius, x, y + radius), fill=color, width=line_width)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=line_width)
            output.parent.mkdir(parents=True, exist_ok=True)
            image.save(output)
    except Exception as exc:
        return {"rendered": False, "reason": str(exc), "path": str(source)}

    return {"rendered": True, "path": str(output), "point_count": len(markers)}


def _marker_point(marker: dict[str, Any], width: int, height: int) -> tuple[int, int] | None:
    try:
        if str(marker.get("coordinate_space") or "").lower() in {"normalized", "normalized_1000"}:
            x = round(float(marker.get("normalized_x", marker.get("x", 0))) * max(width - 1, 0) / 1000)
            y = round(float(marker.get("normalized_y", marker.get("y", 0))) * max(height - 1, 0) / 1000)
        else:
            x = round(float(marker.get("x", 0)))
            y = round(float(marker.get("y", 0)))
    except Exception:
        return None
    return max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1))


def _copy_if_possible(source: Path, output: Path) -> bool:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        return True
    except Exception:
        return False
