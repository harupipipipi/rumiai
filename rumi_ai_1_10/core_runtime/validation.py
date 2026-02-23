"""
validation.py - 共通バリデーションレイヤー (Wave 12 T-049)

pack_api_server.py と capability_installer.py に散在していた
バリデーションロジックを統一的に提供する内部モジュール。

設計原則:
- stdlib のみに依存（循環参照を作らない）
- バリデーション結果は bool または Tuple[bool, Optional[str]] で統一
- 元モジュールの後方互換ラッパーから呼ばれることを想定
- スレッドセーフ（状態を持たない純粋関数のみ）
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple


# ======================================================================
# 定数（正規表現パターン）
# ======================================================================

# pack_id バリデーション: 英数字・アンダースコア・ハイフンのみ、1〜64文字
PACK_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# 汎用 ID バリデーション: staging_id, privilege_id, flow_id, candidate_key 等
SAFE_ID_RE = re.compile(r'^[a-zA-Z0-9_.:/-]{1,256}$')

# slug バリデーション: 英数字・アンダースコア・ハイフンのみ (長さ制限なし)
SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# リクエストボディサイズ上限 (10 MB)
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


# ======================================================================
# ID / 文字列バリデーション
# ======================================================================

def validate_pack_id(pack_id: str) -> bool:
    """pack_id が安全なパターンに合致するか検証する。

    許可パターン: ^[a-zA-Z0-9_-]{1,64}$

    Args:
        pack_id: 検証対象の pack_id 文字列。

    Returns:
        True なら有効、False なら無効。
    """
    return bool(pack_id and PACK_ID_RE.match(pack_id))


def is_safe_id(value: str) -> bool:
    """汎用 ID バリデーション。

    staging_id, privilege_id, flow_id, candidate_key 等に使用する。
    許可パターン: ^[a-zA-Z0-9_.:/-]{1,256}$

    Args:
        value: 検証対象の文字列。

    Returns:
        True なら有効、False なら無効。
    """
    return bool(value and SAFE_ID_RE.match(value))


def validate_slug(slug: str) -> Tuple[bool, Optional[str]]:
    """slug が安全な文字のみで構成されているか検証する。

    許可パターン: ^[a-zA-Z0-9_-]+$

    Args:
        slug: 検証対象の slug 文字列。

    Returns:
        (valid, error_message) のタプル。valid が True なら error_message は None。
    """
    if not slug:
        return False, "slug is empty"
    if not SLUG_PATTERN.match(slug):
        return False, f"Invalid slug (must match [a-zA-Z0-9_-]+): {slug!r}"
    return True, None


# ======================================================================
# パス / ファイルシステムバリデーション
# ======================================================================

def check_no_symlinks(*paths: Path) -> Tuple[bool, Optional[str]]:
    """指定されたパスがシンボリックリンクでないことを確認する。

    Args:
        *paths: 検証対象の Path オブジェクト群。

    Returns:
        (valid, error_message) のタプル。valid が True なら error_message は None。
    """
    for p in paths:
        if os.path.islink(p):
            return False, f"Symbolic link detected (security risk): {p}"
    return True, None


def check_path_within(target: Path, base: Path) -> Tuple[bool, Optional[str]]:
    """target が base ディレクトリ配下にあることを確認する。

    resolve() を使用してシンボリックリンクを解決した上で検証する。

    Args:
        target: 検証対象のパス。
        base: 基準ディレクトリ。

    Returns:
        (valid, error_message) のタプル。valid が True なら error_message は None。
    """
    try:
        resolved_target = target.resolve()
        resolved_base = base.resolve()
        resolved_target.relative_to(resolved_base)
    except (ValueError, OSError):
        return False, f"Path traversal detected: {target} is not within {base}"
    return True, None


def validate_entrypoint(
    entrypoint: str,
    slug_dir: Path,
) -> Tuple[bool, Optional[str], Optional[Path]]:
    """entrypoint を検証する。

    entrypoint は "file:func" 形式であること、パストラバーサルを含まないこと、
    対象ファイルが slug_dir 配下に存在することを検証する。

    Args:
        entrypoint: "file.py:function_name" 形式の文字列。
        slug_dir: entrypoint の基準ディレクトリ。

    Returns:
        (valid, error_message, handler_py_path) のタプル。
        valid が True なら error_message は None、handler_py_path はファイルパス。
        valid が False なら handler_py_path は None。
    """
    if ":" not in entrypoint:
        return (
            False,
            f"Invalid entrypoint format (expected 'file:func'): {entrypoint}",
            None,
        )

    ep_file, ep_func = entrypoint.rsplit(":", 1)

    if not ep_file or not ep_func:
        return False, f"Invalid entrypoint format: {entrypoint}", None

    # パストラバーサル検証 (文字列レベル)
    parts = ep_file.replace("\\", "/").split("/")
    if ".." in parts:
        return (
            False,
            f"Path traversal detected in entrypoint: {entrypoint}",
            None,
        )

    handler_py_path = slug_dir / ep_file

    # resolve() して slug_dir 配下であることを確認
    path_ok, _path_error = check_path_within(handler_py_path, slug_dir)
    if not path_ok:
        return (
            False,
            f"Path traversal detected in entrypoint (resolve): {entrypoint}",
            None,
        )

    if not handler_py_path.exists():
        return False, f"Entrypoint file not found: {ep_file}", None

    return True, None, handler_py_path
