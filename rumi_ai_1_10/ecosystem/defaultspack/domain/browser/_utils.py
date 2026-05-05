from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


def default_browser_root() -> Path:
    env_value = os.environ.get("RUMI_DEFAULTSPACK_BROWSER_ROOT")
    if env_value:
        return Path(env_value)
    pack_root = Path(__file__).resolve().parents[2]
    return pack_root / "user_data" / "shared" / "browser_v2"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sanitize_id(value: Any, *, default: str = "default", max_length: int = 80) -> str:
    raw = str(value or default).strip().lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-_")
    return (cleaned or default)[:max_length]


def read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
