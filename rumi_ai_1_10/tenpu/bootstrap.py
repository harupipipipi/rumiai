#!/usr/bin/env python3
"""
Rumi AI Bootstrap - セットアップエントリポイント

Usage:
    python bootstrap.py              # 対話モード（CLI/Web選択）
    python bootstrap.py --cli        # CLIモード
    python bootstrap.py --cli check  # 環境チェック
    python bootstrap.py --cli init   # 初期セットアップ
    python bootstrap.py --cli recover # リカバリー
    python bootstrap.py --cli run    # アプリ起動
    python bootstrap.py --web        # Webモード（ブラウザUI）
    python bootstrap.py --web --port 5001
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Rumi AI セットアップツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--cli",
        action="store_true",
        help="CLIモードで実行"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Webモードで実行（ブラウザUI）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Webモードのポート番号（デフォルト: 8080）"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["check", "init", "recover", "reset", "doctor", "run"],
        help="CLIコマンド"
    )
    
    args = parser.parse_args()
    
    # モード未指定の場合は対話的に選択
    if not args.cli and not args.web:
        mode = prompt_mode_selection()
        if mode == "cli":
            args.cli = True
        elif mode == "web":
            args.web = True
        else:
            print("キャンセルしました")
            sys.exit(0)
    
    if args.cli:
        run_cli(args.command)
    elif args.web:
        run_web(args.port)


def prompt_mode_selection() -> str:
    """対話的にモードを選択"""
    print("")
    print("╔════════════════════════════════════════════╗")
    print("║    🌸 Rumi AI セットアップ              ║")
    print("╠════════════════════════════════════════════╣")
    print("║                                            ║")
    print("║    1. CLI モード（ターミナル操作）          ║")
    print("║    2. Web モード（ブラウザ操作）           ║")
    print("║    q. 終了                                 ║")
    print("║                                            ║")
    print("╚════════════════════════════════════════════╝")
    print("")
    
    while True:
        try:
            choice = input("選択してください [1/2/q]: ").strip().lower()
            if choice in ("1", "cli"):
                return "cli"
            elif choice in ("2", "web"):
                return "web"
            elif choice in ("q", "quit", "exit"):
                return "quit"
            else:
                print("1, 2, または q を入力してください")
        except (KeyboardInterrupt, EOFError):
            print("")
            return "quit"


def run_cli(command: str = None):
    """CLIモードを実行"""
    try:
        from rumi_setup.cli import run_cli_mode
        run_cli_mode(command)
    except ImportError as e:
        print(f"エラー: CLIモジュールの読み込みに失敗しました: {e}")
        print("rumi_setup/cli/ ディレクトリを確認してください")
        sys.exit(1)


def run_web(port: int):
    """Webモードを実行"""
    try:
        from rumi_setup.web import run_web_mode
        run_web_mode(port)
    except ImportError as e:
        print(f"エラー: Webモジュールの読み込みに失敗しました: {e}")
        print("Flaskがインストールされているか確認してください:")
        print("  pip install flask")
        sys.exit(1)


if __name__ == "__main__":
    main()
