"""
deploy.py - 不要ファイル削除スクリプト

新セキュリティシステムへの移行に伴い、
不要になったファイルを削除する。

使用方法:
    python deploy.py          # ドライラン（削除せずに確認）
    python deploy.py --execute  # 実際に削除
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime


# 削除対象ファイル/ディレクトリ一覧
FILES_TO_DELETE = [
    # 旧Docker handlers（公式は具体的なhandlerを提供しない）
    "docker/core/handlers/file_read.py",
    "docker/core/handlers/file_write.py",
    "docker/core/handlers/env_read.py",
    "docker/core/handlers/network.py",
    "docker/core/handlers/terminal.py",
    "docker/core/handlers/__init__.py",
    
    # 旧Docker host_handlers
    "docker/core/host_handlers/pyautogui_handler.py",
    "docker/core/host_handlers/clipboard_handler.py",
    "docker/core/host_handlers/system_info_handler.py",
    "docker/core/host_handlers/__init__.py",
    
    # 旧Docker scopes
    "docker/core/scopes/file_read.json",
    "docker/core/scopes/file_write.json",
    "docker/core/scopes/env_read.json",
    "docker/core/scopes/network.json",
    "docker/core/scopes/terminal.json",
    "docker/core/scopes/host_pyautogui.json",
    "docker/core/scopes/host_clipboard.json",
    "docker/core/scopes/host_system_info.json",
    
    # 旧サンドボックス実装（新アーキテクチャで置換）
    "core_runtime/sandbox_bridge.py",
    "core_runtime/sandbox_container.py",
    "core_runtime/permission_bridge.py",
    "core_runtime/host_handler_manager.py",
    "core_runtime/docker_manager.py",
    "core_runtime/ecosystem_migrator.py",
    
    # 旧Docker設定
    "docker/config.json",
    "docker/docker-compose.yml",
    
    # 旧handlersディレクトリ（docker/直下）
    "docker/handlers/file_read.py",
    "docker/handlers/file_write.py",
    "docker/handlers/env_read.py",
    "docker/handlers/network.py",
    "docker/handlers/terminal.py",
    "docker/handlers/__init__.py",
    
    # 旧scopesディレクトリ（docker/直下）
    "docker/scopes/file_read.json",
    "docker/scopes/file_write.json",
    "docker/scopes/env_read.json",
    "docker/scopes/network.json",
    "docker/scopes/terminal.json",
    
    # 旧baseディレクトリ（docker/直下）
    "docker/base/Dockerfile",
    
    # 旧packsディレクトリ
    "docker/packs/default/Dockerfile",
]

# 削除対象ディレクトリ一覧（空になったら削除）
DIRECTORIES_TO_DELETE = [
    "docker/core/handlers",
    "docker/core/host_handlers",
    "docker/core/scopes",
    "docker/handlers",
    "docker/scopes",
    "docker/base",
    "docker/packs/default",
    "docker/packs",
    "docker/grants",
    "docker/sandbox",
    "docker/sandbox/default",
    
    # 旧ecosystem（デフォルトPackは削除予定の場合）
    # "ecosystem/default",
    # "ecosystem/lib_flow_constructs",
]


def get_timestamp() -> str:
    """タイムスタンプを取得"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def delete_file(path: Path, dry_run: bool = True) -> bool:
    """ファイルを削除"""
    if not path.exists():
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would delete file: {path}")
        return True
    
    try:
        path.unlink()
        print(f"  [DELETED] File: {path}")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to delete {path}: {e}")
        return False


def delete_directory(path: Path, dry_run: bool = True) -> bool:
    """ディレクトリを削除（空の場合のみ、または強制削除）"""
    if not path.exists():
        return False
    
    if not path.is_dir():
        return False
    
    # ディレクトリが空かチェック
    contents = list(path.iterdir())
    
    # __pycache__ のみの場合は削除対象
    non_cache_contents = [c for c in contents if c.name != "__pycache__"]
    
    if non_cache_contents:
        if dry_run:
            print(f"  [DRY RUN] Would skip non-empty directory: {path}")
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would delete directory: {path}")
        return True
    
    try:
        shutil.rmtree(path)
        print(f"  [DELETED] Directory: {path}")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to delete {path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Delete obsolete files from Rumi AI project"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete files (default is dry run)"
    )
    parser.add_argument(
        "--include-ecosystem",
        action="store_true",
        help="Also delete ecosystem/default and ecosystem/lib_flow_constructs"
    )
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print("=" * 60)
    print("Rumi AI - Obsolete File Cleanup")
    print("=" * 60)
    print(f"Timestamp: {get_timestamp()}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print("=" * 60)
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No files will be deleted")
        print("   Run with --execute to actually delete files\n")
    else:
        print("\n🔴 EXECUTE MODE - Files will be permanently deleted\n")
    
    # ファイル削除
    print("\n--- Files ---\n")
    files_deleted = 0
    files_not_found = 0
    files_error = 0
    
    for file_path_str in FILES_TO_DELETE:
        path = Path(file_path_str)
        if not path.exists():
            print(f"  [NOT FOUND] {path}")
            files_not_found += 1
            continue
        
        if delete_file(path, dry_run):
            files_deleted += 1
        else:
            files_error += 1
    
    # ecosystem削除（オプション）
    if args.include_ecosystem:
        ecosystem_dirs = [
            "ecosystem/default",
            "ecosystem/lib_flow_constructs",
        ]
        for dir_path_str in ecosystem_dirs:
            path = Path(dir_path_str)
            if path.exists() and path.is_dir():
                if dry_run:
                    print(f"  [DRY RUN] Would delete ecosystem directory: {path}")
                    files_deleted += 1
                else:
                    try:
                        shutil.rmtree(path)
                        print(f"  [DELETED] Ecosystem directory: {path}")
                        files_deleted += 1
                    except Exception as e:
                        print(f"  [ERROR] Failed to delete {path}: {e}")
                        files_error += 1
    
    # ディレクトリ削除
    print("\n--- Directories (empty only) ---\n")
    dirs_deleted = 0
    dirs_skipped = 0
    
    for dir_path_str in DIRECTORIES_TO_DELETE:
        path = Path(dir_path_str)
        if not path.exists():
            continue
        
        if delete_directory(path, dry_run):
            dirs_deleted += 1
        else:
            dirs_skipped += 1
    
    # サマリー
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Files deleted:     {files_deleted}")
    print(f"Files not found:   {files_not_found}")
    print(f"Files error:       {files_error}")
    print(f"Directories deleted: {dirs_deleted}")
    print(f"Directories skipped: {dirs_skipped}")
    print("=" * 60)
    
    if dry_run:
        print("\n✅ Dry run complete. Run with --execute to delete files.")
    else:
        print("\n✅ Cleanup complete.")
    
    return 0


if __name__ == "__main__":
    exit(main())
