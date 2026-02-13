#!/usr/bin/env python3
"""
deploy.py - エコシステム起動パス修正の適用スクリプト

プロジェクトルートから実行:
    python deploy.py [--dry-run] [--no-backup]

適用する修正:
  1. flows/00_startup.flow.yaml        — kernel:api.init ステップ追加
  2. core_runtime/kernel_handlers_runtime.py — _h_lib_process_all デフォルト値修正
  3. backend_core/ecosystem/initializer.py   — Registry 初期化パス分岐除去

各修正は冪等（既に適用済みならスキップ）。
デフォルトで .bak バックアップを作成。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple


# ======================================================================
# 設定
# ======================================================================

PATCHES: list[dict] = []

# --- Patch 1: 00_startup.flow.yaml -----------------------------------

YAML_FILE = Path("flows/00_startup.flow.yaml")

API_INIT_BLOCK = textwrap.dedent("""\

  - id: api_init
    phase: security
    priority: 40
    type: handler
    input:
      handler: "kernel:api.init"
      args:
        host: "127.0.0.1"
        port: 8765
""")

# 挿入アンカー: approval_scan ブロックの直後（"# === ecosystem phase ===" の直前）
YAML_ANCHOR = "  # === ecosystem phase ==="
YAML_ALREADY_APPLIED_MARKER = "id: api_init"


# --- Patch 2: kernel_handlers_runtime.py ------------------------------

RUNTIME_FILE = Path("core_runtime/kernel_handlers_runtime.py")

RUNTIME_OLD = 'args.get("packs_dir", "ecosystem/packs")'
RUNTIME_NEW = 'args.get("packs_dir", "ecosystem")'


# --- Patch 3: initializer.py -----------------------------------------

INITIALIZER_FILE = Path("backend_core/ecosystem/initializer.py")

INITIALIZER_OLD_LINES = [
    '        # ecosystem_dir/packs が存在するならそちらを優先、なければそのまま使用',
    '        packs_dir = self.ecosystem_dir / "packs"',
    '        if packs_dir.exists() and packs_dir.is_dir():',
    '            actual_ecosystem_dir = packs_dir',
    '        else:',
    '            actual_ecosystem_dir = self.ecosystem_dir',
]

INITIALIZER_NEW_LINES = [
    '        # Registry 内部の探索ロジック（ecosystem/* + ecosystem/packs/* 互換）に委ねる',
    '        actual_ecosystem_dir = self.ecosystem_dir',
]


# ======================================================================
# ユーティリティ
# ======================================================================

class PatchResult:
    def __init__(self, name: str):
        self.name = name
        self.status: str = "pending"   # pending | applied | skipped | failed
        self.message: str = ""
        self.backup_path: str | None = None


def backup_file(path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bak = path.with_suffix(f"{path.suffix}.{ts}.bak")
    shutil.copy2(path, bak)
    return bak


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ======================================================================
# Patch 1: YAML — api_init ステップ追加
# ======================================================================

def apply_patch_yaml(dry_run: bool, do_backup: bool) -> PatchResult:
    r = PatchResult("flows/00_startup.flow.yaml — api_init 追加")

    if not YAML_FILE.exists():
        r.status = "failed"
        r.message = f"ファイルが見つかりません: {YAML_FILE}"
        return r

    content = read_text(YAML_FILE)

    # 冪等チェック
    if YAML_ALREADY_APPLIED_MARKER in content:
        r.status = "skipped"
        r.message = "既に api_init ステップが存在します"
        return r

    # アンカーの検出
    if YAML_ANCHOR not in content:
        r.status = "failed"
        r.message = f"挿入アンカーが見つかりません: '{YAML_ANCHOR}'"
        return r

    # 挿入
    new_content = content.replace(
        YAML_ANCHOR,
        API_INIT_BLOCK + YAML_ANCHOR,
        1,  # 最初の1箇所のみ
    )

    if dry_run:
        r.status = "applied"
        r.message = "[dry-run] api_init ブロックを挿入します"
        return r

    if do_backup:
        r.backup_path = str(backup_file(YAML_FILE))

    write_text(YAML_FILE, new_content)
    r.status = "applied"
    r.message = "api_init ステップを security phase (priority:40) に追加しました"
    return r


# ======================================================================
# Patch 2: kernel_handlers_runtime.py — デフォルト値修正
# ======================================================================

def apply_patch_runtime(dry_run: bool, do_backup: bool) -> PatchResult:
    r = PatchResult("kernel_handlers_runtime.py — packs_dir デフォルト修正")

    if not RUNTIME_FILE.exists():
        r.status = "failed"
        r.message = f"ファイルが見つかりません: {RUNTIME_FILE}"
        return r

    content = read_text(RUNTIME_FILE)

    # 冪等チェック: 新しい値が既に存在し、古い値が存在しない
    if RUNTIME_NEW in content and RUNTIME_OLD not in content:
        r.status = "skipped"
        r.message = "既に修正済みです"
        return r

    if RUNTIME_OLD not in content:
        r.status = "failed"
        r.message = f"置換対象が見つかりません: '{RUNTIME_OLD}'"
        return r

    new_content = content.replace(RUNTIME_OLD, RUNTIME_NEW, 1)

    if dry_run:
        r.status = "applied"
        r.message = '[dry-run] "ecosystem/packs" → "ecosystem" に変更します'
        return r

    if do_backup:
        r.backup_path = str(backup_file(RUNTIME_FILE))

    write_text(RUNTIME_FILE, new_content)
    r.status = "applied"
    r.message = '_h_lib_process_all のデフォルト packs_dir を "ecosystem" に修正しました'
    return r


# ======================================================================
# Patch 3: initializer.py — Registry 初期化パス修正
# ======================================================================

def apply_patch_initializer(dry_run: bool, do_backup: bool) -> PatchResult:
    r = PatchResult("initializer.py — Registry 初期化パス修正")

    if not INITIALIZER_FILE.exists():
        r.status = "failed"
        r.message = f"ファイルが見つかりません: {INITIALIZER_FILE}"
        return r

    content = read_text(INITIALIZER_FILE)
    lines = content.splitlines(keepends=True)

    # 冪等チェック: 新しいコメント行が既に存在する
    new_comment = INITIALIZER_NEW_LINES[0].strip()
    if any(new_comment in line for line in lines):
        # 旧コードも残っていないか確認
        old_marker = INITIALIZER_OLD_LINES[1].strip()
        if not any(old_marker in line for line in lines):
            r.status = "skipped"
            r.message = "既に修正済みです"
            return r

    # 旧ブロックの開始行を探す
    old_first = INITIALIZER_OLD_LINES[0].strip()
    start_idx = None
    for i, line in enumerate(lines):
        if old_first in line:
            start_idx = i
            break

    if start_idx is None:
        r.status = "failed"
        r.message = f"置換対象ブロックが見つかりません: '{old_first}'"
        return r

    # 旧ブロックが期待通りの並びか検証
    end_idx = start_idx + len(INITIALIZER_OLD_LINES)
    if end_idx > len(lines):
        r.status = "failed"
        r.message = "置換対象ブロックが途中で終わっています"
        return r

    for offset, expected in enumerate(INITIALIZER_OLD_LINES):
        actual = lines[start_idx + offset].rstrip("\n").rstrip("\r")
        if actual != expected:
            r.status = "failed"
            r.message = (
                f"置換対象ブロックの {offset+1} 行目が一致しません\n"
                f"  期待: {expected!r}\n"
                f"  実際: {actual!r}"
            )
            return r

    # 置換の実行
    new_block_lines = [line + "\n" for line in INITIALIZER_NEW_LINES]
    new_lines = lines[:start_idx] + new_block_lines + lines[end_idx:]
    new_content = "".join(new_lines)

    if dry_run:
        r.status = "applied"
        r.message = "[dry-run] 分岐ロジック（6行）を削除し、直接代入（2行）に置換します"
        return r

    if do_backup:
        r.backup_path = str(backup_file(INITIALIZER_FILE))

    write_text(INITIALIZER_FILE, new_content)
    r.status = "applied"
    r.message = "packs_dir 分岐ロジックを除去し、常に self.ecosystem_dir を使用するように修正しました"
    return r


# ======================================================================
# メイン
# ======================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="エコシステム起動パス修正を適用する"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際のファイル変更を行わず、適用内容を表示する",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="バックアップファイル(.bak)を作成しない",
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    do_backup = not args.no_backup

    print("=" * 60)
    print("  deploy.py — エコシステム起動パス修正")
    print(f"  実行時刻: {datetime.now(timezone.utc).isoformat()}")
    print(f"  モード: {'dry-run' if dry_run else '適用'}")
    print(f"  バックアップ: {'有効' if do_backup else '無効'}")
    print("=" * 60)
    print()

    patches = [
        apply_patch_yaml,
        apply_patch_runtime,
        apply_patch_initializer,
    ]

    results: list[PatchResult] = []
    for patch_fn in patches:
        result = patch_fn(dry_run, do_backup)
        results.append(result)

    # 結果表示
    STATUS_ICON = {
        "applied": "✓",
        "skipped": "–",
        "failed": "✗",
        "pending": "?",
    }

    print("-" * 60)
    has_failure = False
    for r in results:
        icon = STATUS_ICON.get(r.status, "?")
        print(f"  [{icon}] {r.name}")
        print(f"      状態: {r.status}")
        print(f"      {r.message}")
        if r.backup_path:
            print(f"      バックアップ: {r.backup_path}")
        print()
        if r.status == "failed":
            has_failure = True

    print("-" * 60)

    applied = sum(1 for r in results if r.status == "applied")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    print(f"  適用: {applied}  スキップ: {skipped}  失敗: {failed}")
    print()

    if has_failure:
        print("  ⚠ 一部の修正に失敗しました。上記のエラーメッセージを確認してください。")
        return 1

    if dry_run:
        print("  dry-run モードのため、ファイルは変更されていません。")
        print("  実際に適用するには --dry-run を外して再実行してください。")
    else:
        print("  全ての修正が正常に完了しました。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
