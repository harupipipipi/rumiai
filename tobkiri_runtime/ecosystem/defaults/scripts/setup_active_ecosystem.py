#!/usr/bin/env python3
"""
setup_active_ecosystem.py - active_ecosystem.json を作成/更新するスクリプト

カーネルのルートディレクトリ (tobkiri_runtime/) から実行すること:
    cd /path/to/tobkiri_runtime
    python /path/to/defaults_pack/scripts/setup_active_ecosystem.py

処理内容:
    1. user_data/active_ecosystem.json のパスを決定
    2. ActiveEcosystemManager を初期化
    3. active_pack_identity を "github:harupipipipi/rumiai-defaults" に設定
    4. HMAC 署名付きで保存（自動）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PACK_IDENTITY = "github:harupipipipi/rumiai-defaults"


def _resolve_kernel_root() -> Path:
    """
    カーネルルートディレクトリを特定する。

    判定基準: CWD に core_runtime/paths.py が存在するか。
    """
    cwd = Path.cwd()
    marker = cwd / "core_runtime" / "paths.py"
    if marker.is_file():
        return cwd
    print("ERROR: カーネルルートディレクトリから実行してください。")
    print(f"  現在のディレクトリ: {cwd}")
    print("  期待する構造: tobkiri_runtime/core_runtime/paths.py が存在すること")
    print("")
    print("対処法:")
    print("  cd /path/to/tobkiri_runtime")
    print("  python /path/to/defaults_pack/scripts/setup_active_ecosystem.py")
    sys.exit(1)


def main() -> None:
    kernel_root = _resolve_kernel_root()

    # カーネルモジュールをインポート可能にする
    kernel_root_str = str(kernel_root)
    if kernel_root_str not in sys.path:
        sys.path.insert(0, kernel_root_str)

    # --- config_path を決定 ---
    config_path = kernel_root / "user_data" / "active_ecosystem.json"

    # --- カーネルモジュールのインポート ---
    try:
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
    except ImportError as exc:
        print(f"ERROR: カーネルモジュールの読み込みに失敗しました: {exc}")
        print("")
        print("対処法:")
        print("  1. pip install pyyaml cryptography")
        print("  2. カーネルルートディレクトリから実行しているか確認")
        sys.exit(1)

    # --- 既存ファイルの確認 ---
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            current_identity = existing.get("active_pack_identity")
            print(f"[setup_active_ecosystem] 既存の active_ecosystem.json を検出")
            print(f"  パス: {config_path}")
            print(f"  現在の active_pack_identity: {current_identity}")
            if current_identity == _PACK_IDENTITY:
                print(f"[setup_active_ecosystem] 既に '{_PACK_IDENTITY}' が設定されています。")
                print("  再署名のため上書き保存を実行します...")
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[setup_active_ecosystem] 既存ファイルの読み込みに失敗: {exc}")
            print("  新規作成で上書きします...")

    # --- ActiveEcosystemManager を初期化 ---
    print("[setup_active_ecosystem] ActiveEcosystemManager を初期化中...")
    try:
        manager = ActiveEcosystemManager(config_path=str(config_path))
    except Exception as exc:
        print(f"ERROR: ActiveEcosystemManager の初期化に失敗しました: {exc}")
        print("")
        print("対処法:")
        print("  1. user_data/ ディレクトリへの書き込み権限を確認")
        print("  2. user_data/permissions/.secret_key の読み書き権限を確認")
        print("     (初回実行時は自動生成されます)")
        sys.exit(1)

    # --- active_pack_identity を設定 ---
    print(f"[setup_active_ecosystem] active_pack_identity = '{_PACK_IDENTITY}' を設定中...")
    try:
        manager.active_pack_identity = _PACK_IDENTITY
    except Exception as exc:
        print(f"ERROR: 設定の保存に失敗しました: {exc}")
        print("")
        print("対処法:")
        print(f"  {config_path.parent}/ への書き込み権限を確認してください。")
        sys.exit(1)

    # --- 結果の確認 ---
    saved_identity = manager.active_pack_identity
    if saved_identity == _PACK_IDENTITY:
        print(f"[setup_active_ecosystem] 設定完了!")
        print(f"  ファイル: {config_path}")
        print(f"  active_pack_identity: {saved_identity}")
        print(f"  HMAC署名: 自動付与済み")
    else:
        print(f"ERROR: 設定の保存に失敗した可能性があります。")
        print(f"  期待値: '{_PACK_IDENTITY}'")
        print(f"  実際値: {saved_identity}")
        sys.exit(1)

    # --- ファイル内容の表示 ---
    if config_path.is_file():
        print("")
        print("--- active_ecosystem.json の内容 ---")
        with open(config_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        # HMAC署名は長いので省略表示
        sig = content.get("_hmac_signature", "")
        if sig:
            content["_hmac_signature"] = sig[:16] + "..." + sig[-16:]
        print(json.dumps(content, ensure_ascii=False, indent=2))
        print("------------------------------------")


if __name__ == "__main__":
    main()
