"""
api_response.py - APIResponse データクラス

Pack API ハンドラ共通のレスポンス型。
pack_api_server.py から抽出し、循環 import を解消する。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


__all__ = ["APIResponse"]
