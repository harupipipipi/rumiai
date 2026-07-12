from __future__ import annotations

from pathlib import Path
from typing import Any

from core_runtime.pack_trust import is_pack_trusted


TRUSTED_BUILTIN_PROMPT_PACK_IDS = {
    "defaultspack",
    "rumi_default_tools_pack",
    "rumi_operations_company_pack",
}


def _bundled_prompt_pack_root(pack_id: str) -> Path | None:
    if pack_id == "defaultspack":
        pack_root = Path(__file__).resolve().parents[2]
        return pack_root if (pack_root / "ecosystem.json").is_file() else None
    ecosystem_root = Path(__file__).resolve().parents[3]
    pack_root = ecosystem_root / pack_id
    return pack_root if pack_root.is_dir() and (pack_root / "ecosystem.json").is_file() else None


def _source_path_within_pack(source_path: str | Path | None, pack_root: Path | None) -> bool:
    if pack_root is None:
        return False
    if source_path in (None, ""):
        return True
    try:
        Path(source_path).resolve().relative_to(pack_root.resolve())
        return True
    except (OSError, ValueError):
        return False


def is_trusted_prompt_pack(pack_id: str, approval_manager: Any = None) -> tuple[bool, str | None]:
    normalized = str(pack_id or "").strip()
    if normalized in TRUSTED_BUILTIN_PROMPT_PACK_IDS and _bundled_prompt_pack_root(normalized) is not None:
        return True, None
    return is_pack_trusted(pack_id, approval_manager=approval_manager)


def prompt_pack_is_trusted(pack_id: str, approval_manager: Any = None) -> bool:
    trusted, _reason = is_trusted_prompt_pack(pack_id, approval_manager=approval_manager)
    return trusted


def prompt_pack_source_is_trusted(
    pack_id: str,
    source_path: str | Path | None = None,
    approval_manager: Any = None,
) -> bool:
    normalized = str(pack_id or "").strip()
    if normalized in TRUSTED_BUILTIN_PROMPT_PACK_IDS:
        return _source_path_within_pack(source_path, _bundled_prompt_pack_root(normalized))
    trusted, _reason = is_pack_trusted(normalized, approval_manager=approval_manager)
    return trusted
