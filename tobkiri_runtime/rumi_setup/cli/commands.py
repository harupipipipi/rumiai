"""
CLI コマンド
"""

import sys
from typing import Optional

from ..core import (
    EnvironmentChecker,
    Initializer,
    Recovery,
    PackInstaller,
    AppRunner,
    get_state
)


class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"


def _supports_color() -> bool:
    if sys.platform == "win32":
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()


def c(color: str, text: str) -> str:
    if USE_COLOR:
        return f"{color}{text}{Colors.RESET}"
    return text


def icon(status: str) -> str:
    icons = {
        "success": c(Colors.GREEN, "✓"),
        "error": c(Colors.RED, "✗"),
        "warn": c(Colors.YELLOW, "⚠"),
        "info": c(Colors.BLUE, "ℹ"),
        "run": c(Colors.CYAN, "▶"),
    }
    return icons.get(status, " ")


def header(title: str):
    print("")
    print(c(Colors.BOLD, f"{'═' * 50}"))
    print(c(Colors.BOLD, f"  🌸 {title}"))
    print(c(Colors.BOLD, f"{'═' * 50}"))
    print("")


def confirm(message: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        response = input(f"  {message} {suffix}: ").strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("")
        return False


def run_cli_mode(command: Optional[str] = None):
    if command is None:
        show_menu()
        return
    
    if command == "check":
        cmd_check()
    elif command == "init":
        cmd_init()
    elif command == "recover":
        cmd_recover()
    elif command == "doctor":
        cmd_doctor()
    elif command == "reset":
        cmd_reset()
    elif command == "run":
        cmd_run()
    else:
        print(f"Unknown command: {command}")
        print("Available: check, init, recover, doctor, reset, run")


def show_menu():
    header("Rumi AI セットアップ")
    
    print("  1. 環境チェック (check)")
    print("  2. 初期セットアップ (init)")
    print("  3. 診断 (doctor)")
    print("  4. リカバリー (recover)")
    print("  5. リセット (reset)")
    print("  6. アプリ起動 (run)")
    print("  q. 終了")
    print("")
    
    while True:
        try:
            choice = input("選択 [1-6/q]: ").strip().lower()
            
            if choice in ("1", "check"):
                cmd_check()
            elif choice in ("2", "init"):
                cmd_init()
            elif choice in ("3", "doctor"):
                cmd_doctor()
            elif choice in ("4", "recover"):
                cmd_recover()
            elif choice in ("5", "reset"):
                cmd_reset()
            elif choice in ("6", "run"):
                cmd_run()
            elif choice in ("q", "quit", "exit"):
                print("終了します")
                break
            else:
                print("1-6 または q を入力してください")
                continue
            
            print("")
            input("Enter で続行...")
            show_menu()
            break
            
        except (KeyboardInterrupt, EOFError):
            print("\n終了します")
            break


def cmd_check():
    header("環境チェック")
    
    checker = EnvironmentChecker()
    result = checker.check_all()
    
    print("")
    for check in result["checks"]:
        status = "success" if check["available"] else ("warn" if not check["required"] else "error")
        req = "" if check["required"] else " (推奨)"
        ver = f" {check['version']}" if check["version"] else ""
        
        print(f"  {icon(status)} {check['name']}{ver}{req}")
        
        if check["message"] and not check["available"]:
            print(f"      {c(Colors.YELLOW, check['message'])}")
    
    print("")
    if result["success"]:
        print(c(Colors.GREEN, "  ✓ 基本要件を満たしています"))
    else:
        print(c(Colors.RED, "  ✗ 必須の依存関係が不足しています"))


def cmd_init():
    header("初期セットアップ")
    
    print("  以下を作成します:")
    print("    - user_data/ ディレクトリ構造")
    print("    - 設定ファイル")
    print("    - setup pack target（オプション）")
    print("")
    
    if not confirm("続行しますか？"):
        print("  キャンセルしました")
        return
    
    def confirm_default(msg: str) -> bool:
        return confirm(msg)
    
    print("")
    initializer = Initializer()
    result = initializer.initialize(
        install_default=True,
        confirm_callback=confirm_default
    )
    
    state = get_state()
    for log in state.logs:
        print(f"  {icon(log.level)} {log.message}")
    
    print("")
    if result["success"]:
        print(c(Colors.GREEN, "  ✓ セットアップ完了"))
    else:
        print(c(Colors.RED, f"  ✗ エラーが発生しました: {result.get('errors', [])}"))


def cmd_doctor():
    header("システム診断")
    
    recovery = Recovery()
    result = recovery.diagnose()
    
    state = get_state()
    for log in state.logs:
        print(f"  {icon(log.level)} {log.message}")
    
    print("")
    if result["healthy"]:
        print(c(Colors.GREEN, "  ✓ システムは正常です"))
    else:
        counts = result["issue_count"]
        print(c(Colors.YELLOW, f"  ⚠ 問題が見つかりました: エラー {counts['error']}, 警告 {counts['warn']}"))


def cmd_recover():
    header("リカバリー")
    
    print("  システムの問題を検出し、修復を試みます。")
    print("")
    
    if not confirm("続行しますか？"):
        print("  キャンセルしました")
        return
    
    print("")
    recovery = Recovery()
    result = recovery.recover(auto_fix=True)
    
    state = get_state()
    for log in state.logs:
        print(f"  {icon(log.level)} {log.message}")
    
    print("")
    if result["success"]:
        if result["recovered"]:
            print(c(Colors.GREEN, f"  ✓ {len(result['recovered'])} 件を修復しました"))
        else:
            print(c(Colors.GREEN, "  ✓ 修復は不要でした"))
    else:
        print(c(Colors.RED, f"  ✗ 一部の修復に失敗しました"))


def cmd_reset():
    header("リセット")
    
    print(c(Colors.RED, "  ⚠ 警告: この操作は user_data を初期化します"))
    print("    (chats, settings は保持されます)")
    print("")
    
    try:
        confirm_input = input("  本当にリセットしますか？ [yes/N]: ").strip().lower()
        if confirm_input != "yes":
            print("  キャンセルしました")
            return
    except (KeyboardInterrupt, EOFError):
        print("\n  キャンセルしました")
        return
    
    print("")
    print("  リセット機能は現在開発中です")


def cmd_run():
    header("アプリケーション起動")
    
    runner = AppRunner()
    check = runner.is_ready()
    
    if not check["ready"]:
        for issue in check["issues"]:
            print(f"  {icon('error')} {issue}")
        print("")
        print(c(Colors.RED, "  ✗ 実行準備ができていません"))
        print("  先に init を実行してください")
        return
    
    print(f"  {icon('info')} venv Python: {check['venv_python']}")
    print(f"  {icon('info')} app.py: {check['app_path']}")
    print("")
    
    if not confirm("アプリケーションを起動しますか？"):
        print("  キャンセルしました")
        return
    
    print("")
    print(f"  {icon('run')} 起動中...")
    print("")
    
    result = runner.run(background=False)
    
    if not result["success"]:
        print(c(Colors.RED, f"  ✗ 起動に失敗しました: {result.get('error', 'unknown')}"))
