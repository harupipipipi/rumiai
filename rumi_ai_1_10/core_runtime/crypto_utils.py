"""
crypto_utils.py - 暗号ユーティリティ

ファイルハッシュ計算など、暗号関連のヘルパー関数を提供する。
capability_handler_registry.py / capability_executor.py が依存していた
compute_file_sha256 を統一配置する。

Phase D: D0-3 依存解消のために新規作成。
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
