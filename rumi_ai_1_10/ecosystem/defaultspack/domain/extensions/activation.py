from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PACK_ID = "defaultspack"


def rumi_root_for_pack(pack_root: Path | str) -> Path:
    root = Path(pack_root)
    if root.parent.name == "ecosystem":
        return root.parent.parent
    return Path(__file__).resolve().parents[4]


def setup_pack_selection_path(pack_root: Path | str) -> Path:
    return rumi_root_for_pack(pack_root) / "user_data" / "settings" / "setup_pack_selection.json"


def selected_extension_pack_ids(pack_root: Path | str) -> set[str] | None:
    path = setup_pack_selection_path(pack_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    ids: list[str] = []
    _extend_ids(ids, data.get("target_pack_ids"))
    _extend_ids(ids, data.get("installed_target_pack_ids"))
    _extend_ids(ids, data.get("active_target_pack_id"))
    _extend_ids(ids, data.get("target_pack_id"))

    selected = {pack_id for pack_id in ids if pack_id}
    if not selected:
        return None
    selected.add(DEFAULT_PACK_ID)
    return selected


def _extend_ids(result: list[str], value: Any) -> None:
    if isinstance(value, str):
        item = value.strip()
        if item:
            result.append(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
