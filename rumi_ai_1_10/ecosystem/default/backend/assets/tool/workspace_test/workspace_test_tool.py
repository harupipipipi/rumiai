"""
ワークスペーステストツール
AgentRuntimeのワークスペース機能とファイル操作をテストするツール
"""

import json
from datetime import datetime

TOOL_NAME = "ワークスペーステスト"
TOOL_DESCRIPTION = "AgentRuntimeのワークスペース機能をテストします"
TOOL_ICON = "📁"


def get_function_declaration() -> dict:
    """Function Calling用の宣言を返す"""
    return {
        "name": "workspace_test",
        "description": "ワークスペースへのファイル読み書きをテストします。AgentRuntimeが正しく注入されているか確認できます。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "実行するアクション: write, read, list, test_all"
                },
                "filename": {
                    "type": "string",
                    "description": "操作対象のファイル名（write/readで使用）"
                },
                "content": {
                    "type": "string",
                    "description": "書き込む内容（writeで使用）"
                }
            },
            "required": ["action"]
        }
    }


def execute(args: dict, context: dict) -> dict:
    """ツールを実行する"""
    callback = context.get('message_callback')
    runtime = context.get('runtime')
    
    action = args.get('action', 'test_all')
    filename = args.get('filename', 'test.txt')
    content = args.get('content', '')
    
    # RuntimeがなければエラーSUMMA
    if not runtime:
        return {
            "success": False,
            "error": "AgentRuntimeが注入されていません。context['runtime']が存在しません。"
        }
    
    try:
        if callback:
            callback(f"アクション '{action}' を実行中...")
        
        workspace = runtime.workspace()
        
        if action == "write":
            # ファイル書き込みテスト
            if not content:
                content = f"テストファイル - 作成日時: {datetime.now().isoformat()}"
            
            path = workspace.write(filename, content)
            
            return {
                "success": True,
                "result": {
                    "action": "write",
                    "filename": filename,
                    "path": path,
                    "content_length": len(content)
                }
            }
        
        elif action == "read":
            # ファイル読み込みテスト
            if not workspace.exists(filename):
                return {
                    "success": False,
                    "error": f"ファイルが存在しません: {filename}"
                }
            
            content = workspace.read(filename)
            
            return {
                "success": True,
                "result": {
                    "action": "read",
                    "filename": filename,
                    "content": content,
                    "content_length": len(content)
                }
            }
        
        elif action == "list":
            # ファイル一覧取得
            files = workspace.list_files()
            dirs = workspace.list_dirs()
            
            return {
                "success": True,
                "result": {
                    "action": "list",
                    "workspace_path": workspace.get_path(),
                    "files": files,
                    "directories": dirs
                }
            }
        
        elif action == "test_all":
            # 総合テスト
            results = []
            
            # 1. 書き込みテスト
            if callback:
                callback("1/4: 書き込みテスト...")
            test_content = f"AgentRuntime テスト - {datetime.now().isoformat()}"
            write_path = workspace.write("runtime_test.txt", test_content)
            results.append({"test": "write", "success": True, "path": write_path})
            
            # 2. 読み込みテスト
            if callback:
                callback("2/4: 読み込みテスト...")
            read_content = workspace.read("runtime_test.txt")
            read_success = read_content == test_content
            results.append({"test": "read", "success": read_success, "match": read_success})
            
            # 3. 存在確認テスト
            if callback:
                callback("3/4: 存在確認テスト...")
            exists = workspace.exists("runtime_test.txt")
            not_exists = not workspace.exists("nonexistent_file.txt")
            results.append({"test": "exists", "success": exists and not_exists})
            
            # 4. 一覧取得テスト
            if callback:
                callback("4/4: 一覧取得テスト...")
            files = workspace.list_files()
            results.append({"test": "list", "success": True, "file_count": len(files)})
            
            # 共有ストレージテスト
            if callback:
                callback("ボーナス: 共有ストレージテスト...")
            shared = runtime.shared_storage
            shared.write("runtime_test_shared.txt", f"共有ストレージテスト - {datetime.now().isoformat()}")
            shared_files = shared.list_files()
            results.append({"test": "shared_storage", "success": True, "file_count": len(shared_files)})
            
            all_passed = all(r.get("success", False) for r in results)
            
            return {
                "success": True,
                "result": {
                    "action": "test_all",
                    "all_passed": all_passed,
                    "tests": results,
                    "workspace_path": workspace.get_path(),
                    "shared_storage_path": shared.get_path()
                }
            }
        
        else:
            return {
                "success": False,
                "error": f"不明なアクション: {action}。write, read, list, test_all のいずれかを指定してください。"
            }
    
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
