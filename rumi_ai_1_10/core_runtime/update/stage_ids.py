"""Stage id validation shared by update managers."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

_STAGE_ID_RE = re.compile(r"^\d{10}-[0-9a-f]{10}$")


def make_stage_id() -> str:
    return f"{int(time.time())}-{uuid.uuid4().hex[:10]}"


def validate_stage_id(stage_id: str) -> str:
    value = str(stage_id or "").strip()
    if not _STAGE_ID_RE.fullmatch(value):
        raise ValueError("invalid stage_id")
    return value


def resolve_stage_dir(staging_root: Path, stage_id: str, *, allowed_root: Path | None = None) -> Path:
    value = validate_stage_id(stage_id)
    if staging_root.is_symlink():
        raise ValueError("staging root must not be a symlink")
    raw_stage_dir = staging_root / value
    if raw_stage_dir.is_symlink():
        raise ValueError("stage directory must not be a symlink")
    root = staging_root.resolve(strict=False)
    stage_dir = raw_stage_dir.resolve(strict=False)
    try:
        stage_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("stage_id escapes staging root") from exc
    if allowed_root is not None:
        allowed = allowed_root.resolve(strict=False)
        try:
            stage_dir.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("stage_id escapes update root") from exc
    return stage_dir
