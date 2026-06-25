from __future__ import annotations

from typing import Any

from core_runtime.pack_trust import is_pack_trusted


def is_trusted_prompt_pack(pack_id: str, approval_manager: Any = None) -> tuple[bool, str | None]:
    return is_pack_trusted(pack_id, approval_manager=approval_manager)


def prompt_pack_is_trusted(pack_id: str, approval_manager: Any = None) -> bool:
    trusted, _reason = is_trusted_prompt_pack(pack_id, approval_manager=approval_manager)
    return trusted
