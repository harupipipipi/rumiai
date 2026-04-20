#!/usr/bin/env python3
"""
approve_defaults.py - defaults Pack を承認するセットアップスクリプト

カーネルのルートディレクトリ (rumi_ai_1_10/) から実行すること:
    cd /path/to/rumi_ai_1_10
    python /path/to/defaults_pack/scripts/approve_defaults.py

処理内容:
    1. initialize_approval_manager ファクトリで ApprovalManager を初期化
    2. ecosystem/ 配下の Pack をスキャン
    3. "defaults" Pack を検出
    4. approve("defaults") を実行
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_kernel_root() -> Path:
    """
    カーネルルートディレクトリを特定する。

    判定基準: CWD に core_runtime/paths.py が存在するか。
    存在しなければエラーを出して終了する。
    """
    cwd = Path.cwd()
    marker = cwd / "core_runtime" / "paths.py"
    if marker.is_file():
        return cwd
    print("ERROR: カーネルルートディレクトリから実行してください。")
    print(f"  現在のディレクトリ: {cwd}")
    print("  期待する構造: rumi_ai_1_10/core_runtime/paths.py が存在すること")
    print("")
    print("対処法:")
    print("  cd /path/to/rumi_ai_1_10")
    print("  python /path/to/defaults_pack/scripts/approve_defaults.py")
    sys.exit(1)


def main() -> None:
    kernel_root = _resolve_kernel_root()

    # カーネルモジュールをインポート可能にする
    kernel_root_str = str(kernel_root)
    if kernel_root_str not in sys.path:
        sys.path.insert(0, kernel_root_str)

    # --- カーネルモジュールのインポート ---
    try:
        from core_runtime.approval_manager import (
            initialize_approval_manager,
            ApprovalResult,
            PackStatus,
        )
        from core_runtime.paths import ECOSYSTEM_DIR, GRANTS_DIR
    except ImportError as exc:
        print(f"ERROR: カーネルモジュールの読み込みに失敗しました: {exc}")
        print("")
        print("対処法:")
        print("  1. pip install pyyaml cryptography")
        print("  2. カーネルルートディレクトリから実行しているか確認")
        sys.exit(1)

    # --- ecosystem/defaults/ の存在チェック ---
    ecosystem_dir = Path(ECOSYSTEM_DIR)
    defaults_dir = ecosystem_dir / "defaults"
    if not defaults_dir.is_dir():
        print(f"ERROR: defaults Pack が見つかりません: {defaults_dir}")
        print("")
        print("対処法:")
        print(f"  defaults Pack リポジトリを {defaults_dir} に配置してください。")
        print("  例: git clone https://github.com/harupipipipi/rumiai_defaults.git \\")
        print(f"       {defaults_dir}")
        sys.exit(1)

    eco_json = defaults_dir / "ecosystem.json"
    if not eco_json.is_file():
        print(f"ERROR: ecosystem.json が見つかりません: {eco_json}")
        print("")
        print("対処法:")
        print("  defaults Pack のクローンが正しく完了しているか確認してください。")
        sys.exit(1)

    # --- ApprovalManager 初期化（ファクトリ経由）---
    print("[approve_defaults] ApprovalManager を初期化中...")
    try:
        manager = initialize_approval_manager(
            packs_dir=ECOSYSTEM_DIR,
            grants_dir=GRANTS_DIR,
        )
    except Exception as exc:
        print(f"ERROR: ApprovalManager の初期化に失敗しました: {exc}")
        print("")
        print("対処法:")
        print("  user_data/permissions/ への書き込み権限を確認してください。")
        sys.exit(1)

    # --- Pack スキャン ---
    print("[approve_defaults] ecosystem/ 配下の Pack をスキャン中...")
    try:
        discovered = manager.scan_packs()
    except Exception as exc:
        print(f"ERROR: Pack スキャンに失敗しました: {exc}")
        sys.exit(1)

    print(f"[approve_defaults] 検出された Pack: {discovered}")

    if "defaults" not in discovered:
        print("ERROR: 'defaults' Pack がスキャン結果に含まれていません。")
        print("")
        print("対処法:")
        print(f"  1. {defaults_dir}/ecosystem.json が存在するか確認")
        print(f"  2. ecosystem.json 内の pack_id が 'defaults' であるか確認")
        sys.exit(1)

    # --- 既存承認状態の確認 ---
    current_status = manager.get_status("defaults")
    if current_status == PackStatus.APPROVED:
        print("[approve_defaults] defaults Pack は既に承認済みです。")
        print(f"  ステータス: {current_status.value}")

        # ハッシュ検証
        is_valid, reason = manager.is_pack_approved_and_verified("defaults")
        if is_valid:
            print("  ハッシュ検証: OK（ファイル改変なし）")
        else:
            print(f"  ハッシュ検証: NG（理由: {reason}）")
            print("  再承認を実行します...")
            result: ApprovalResult = manager.approve("defaults")
            if result.success:
                print(f"  再承認成功: status={result.status.value}")
            else:
                print(f"  再承認失敗: {result.error}")
                sys.exit(1)
        return

    # --- 承認実行 ---
    print("[approve_defaults] defaults Pack を承認中...")
    try:
        result: ApprovalResult = manager.approve("defaults")
    except Exception as exc:
        print(f"ERROR: 承認処理で例外が発生しました: {exc}")
        sys.exit(1)

    if result.success:
        print(f"[approve_defaults] 承認成功!")
        print(f"  pack_id: {result.pack_id}")
        print(f"  status:  {result.status.value}")

        # 確認: grants ファイルの存在
        grants_file = Path(GRANTS_DIR) / "defaults.grants.json"
        if grants_file.is_file():
            print(f"  grants:  {grants_file}")
        else:
            print(f"  WARNING: grants ファイルが見つかりません: {grants_file}")
    else:
        print(f"ERROR: 承認に失敗しました: {result.error}")
        print("")
        print("対処法:")
        print("  1. defaults Pack のディレクトリ構造が正しいか確認")
        print("  2. ecosystem.json が有効な JSON であるか確認")
        print("  3. user_data/permissions/ への書き込み権限を確認")
        sys.exit(1)


if __name__ == "__main__":
    main()
