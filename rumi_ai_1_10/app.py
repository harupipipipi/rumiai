# app.py
# 機能追加・修正版 (複数ファイルアップロード、ペースト対応、Function Calling対応、パス修正、ストリーミング・強制停止対応、AIマネージャー対応、サポーター対応)

import os
import json
import uuid
import time
import csv
import base64
import tempfile
import shutil
import stat
import time as time_module
import re
import subprocess
import mimetypes
import traceback
import datetime
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_from_directory, abort
from dotenv import load_dotenv
import importlib.util

load_dotenv('.env.local')
app = Flask(__name__)

# パスを追加（tool/ と prompt/ を参照可能にする）
_project_root = Path(__file__).parent
sys.path.insert(0, str(_project_root / "tool"))
sys.path.insert(0, str(_project_root / "prompt"))

# エコシステム初期化（他のマネージャーより先に実行）
try:
    from backend_core.ecosystem import initialize_ecosystem
    from backend_core.ecosystem.compat import mark_ecosystem_initialized
    
    init_result = initialize_ecosystem()
    if init_result['success']:
        mark_ecosystem_initialized()
        print(f"エコシステム初期化成功: {init_result['packs_loaded']}個のPack, {init_result['components_loaded']}個のComponent")
    else:
        print(f"エコシステム初期化に問題があります: {init_result['errors']}")
except ImportError as e:
    print(f"エコシステムモジュールが見つかりません（従来モードで動作）: {e}")
except Exception as e:
    print(f"エコシステム初期化エラー（従来モードで動作）: {e}")
    import traceback
    traceback.print_exc()

# ai_managerを先に初期化
from ai_manager import AIClient

try:
    # ai_managerを初期化（APIキーチェックは各クライアントが行う）
    ai_manager = AIClient()
except ValueError as e:
    print(f"致命的なエラー: {e}")
    ai_manager = None

# PromptLoaderのインポートと初期化
try:
    from prompt_loader import PromptLoader
    prompt_loader = PromptLoader()
    prompt_loader.load_all_prompts()
    print(f"読み込まれたプロンプト数: {len(prompt_loader.loaded_prompts)}")
except ImportError as e:
    print(f"警告: PromptLoaderの読み込みに失敗: {e}")
    prompt_loader = None
except Exception as e:
    print(f"警告: プロンプトの初期化に失敗: {e}")
    import traceback
    traceback.print_exc()
    prompt_loader = None

# SupporterLoaderのインポートと初期化
try:
    from supporter.supporter_loader import SupporterLoader
    supporter_loader = SupporterLoader()
    supporter_loader.load_all_supporters()
    print(f"読み込まれたサポーター数: {len(supporter_loader.loaded_supporters)}")
except ImportError as e:
    print(f"警告: SupporterLoaderの読み込みに失敗: {e}")
    supporter_loader = None
except Exception as e:
    print(f"警告: サポーターの初期化に失敗: {e}")
    import traceback
    traceback.print_exc()
    supporter_loader = None

# SupporterDependencyManagerのインポートと初期化
try:
    from supporter.supporter_dependency_manager import SupporterDependencyManager
    supporter_dependency_manager = SupporterDependencyManager()
except ImportError:
    supporter_dependency_manager = None
except Exception as e:
    print(f"警告: SupporterDependencyManagerの初期化に失敗: {e}")
    supporter_dependency_manager = None

# その後でマネージャーをインポート・初期化
from chat_manager import ChatManager
from message_handler import MessageHandler
from settings_manager import SettingsManager
from tool_ui_manager import tool_ui_manager
from relationship_manager import RelationshipManager

# マネージャーの初期化
chat_manager = ChatManager()
settings_manager = SettingsManager()
relationship_manager = RelationshipManager()

# MessageHandlerにprompt_loader, relationship_manager, supporter_loaderを渡す
if ai_manager:
    message_handler = MessageHandler(
        ai_manager,
        chat_manager,
        prompt_loader,
        relationship_manager,
        supporter_loader
    )
else:
    message_handler = None

# --- ルート定義 ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chats/<chat_id>')
def show_chat(chat_id):
    return render_template('index.html')

# --- APIエンドポイント ---
@app.route('/api/user/settings', methods=['GET', 'POST'])
def user_settings_api():
    if request.method == 'GET':
        return jsonify(settings_manager.get_user_settings())
    elif request.method == 'POST':
        settings_manager.save_user_settings(request.json)
        return jsonify({'success': True}), 200

@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    """利用可能なプロンプトの一覧を取得"""
    if prompt_loader:
        return jsonify(prompt_loader.get_available_prompts())
    else:
        # フォールバック: settings_managerを使用（後方互換性）
        return jsonify(settings_manager.get_available_prompts())

@app.route('/api/prompts/<prompt_id>', methods=['GET'])
def get_prompt_detail(prompt_id):
    """特定のプロンプトの詳細を取得"""
    if not prompt_loader:
        return jsonify({'error': 'Prompt loader not initialized'}), 500
    
    if prompt_id in prompt_loader.loaded_prompts:
        info = prompt_loader.loaded_prompts[prompt_id]
        return jsonify({
            'id': prompt_id,
            'name': info['name'],
            'description': info.get('description', ''),
            'has_venv': info.get('has_venv', False),
            'settings_schema': info.get('settings_schema')
        })
    return jsonify({'error': 'Prompt not found'}), 404

@app.route('/api/prompts/<prompt_id>/settings', methods=['GET', 'POST'])
def handle_prompt_settings(prompt_id):
    """プロンプトの設定を取得/更新"""
    if not prompt_loader:
        return jsonify({'error': 'Prompt loader not initialized'}), 500
    
    if request.method == 'GET':
        settings = prompt_loader.get_prompt_settings(prompt_id)
        return jsonify(settings)
    
    elif request.method == 'POST':
        success = prompt_loader.update_prompt_settings(prompt_id, request.json)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to update settings'}), 500

@app.route('/api/prompts/reload', methods=['POST'])
def reload_prompts():
    """プロンプトを再読み込み"""
    if not prompt_loader:
        return jsonify({'error': 'Prompt loader not initialized'}), 500
    
    result = prompt_loader.reload_all_prompts()
    return jsonify(result)

@app.route('/api/folders', methods=['POST'])
def create_folder():
    data = request.get_json() if request.is_json else {}
    folder_name = data.get('name', '').strip()
    
    try:
        folder_name = chat_manager.create_folder(folder_name)
        return jsonify({'success': True, 'folder_name': folder_name}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats', methods=['GET'])
def get_all_chats():
    return jsonify(chat_manager.get_all_chats())

@app.route('/api/chats', methods=['POST'])
def create_new_chat():
    data = request.get_json() if request.is_json else {}
    folder_name = data.get('folder', None)
    
    metadata = chat_manager.create_chat(folder_name)
    return jsonify(metadata), 201

@app.route('/api/chats/<chat_id>', methods=['GET', 'DELETE', 'PATCH'])
def handle_single_chat(chat_id):
    if request.method == 'DELETE':
        try:
            # チャットに関連するリレーションシップを削除
            deleted_links = relationship_manager.delete_all_links_for(chat_id)
            if deleted_links > 0:
                print(f"Deleted {deleted_links} relationship links for chat {chat_id}")
            
            chat_manager.delete_chat(chat_id)
            return jsonify({'success': True}), 200
        except FileNotFoundError:
            return jsonify({'error': 'Chat not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    if request.method == 'GET':
        try:
            data = chat_manager.load_chat_history(chat_id)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify({
                'metadata': {'title': '新しいチャット', 'is_pinned': False, 'folder': None},
                'messages': []
            })
    
    if request.method == 'PATCH':
        try:
            chat_manager.update_chat_metadata(chat_id, request.json)
            return jsonify({'success': True}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/tools', methods=['GET', 'POST'])
def handle_chat_tools(chat_id):
    """チャットごとのツール設定を取得/更新"""
    
    if request.method == 'GET':
        try:
            # チャット履歴を読み込んで active_tools を取得
            chat_data = chat_manager.load_chat_history(chat_id)
            active_tools = chat_data.get('active_tools')
            
            # 全ツール一覧を取得
            all_tools = []
            if ai_manager and ai_manager.tool_loader:
                for tool_name, tool_info in ai_manager.tool_loader.loaded_tools.items():
                    all_tools.append({
                        'name': tool_name,
                        'display_name': tool_info.get('name', tool_name),
                        'description': tool_info.get('description', ''),
                        'icon': tool_info.get('icon', '🔧'),
                        'enabled': tool_info.get('enabled', True)
                    })
            
            # モードを判定
            if active_tools is None:
                mode = "all"  # 全ツール許可
            elif len(active_tools) == 0:
                mode = "none"  # 全ツール禁止
            else:
                mode = "allowlist"  # 許可リスト
            
            return jsonify({
                'active_tools': active_tools,
                'all_tools': all_tools,
                'mode': mode
            }), 200
            
        except FileNotFoundError:
            return jsonify({'error': 'Chat not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.json
            
            if 'active_tools' not in data:
                return jsonify({'error': 'active_tools field is required'}), 400
            
            active_tools = data['active_tools']
            
            # バリデーション
            if active_tools is not None and not isinstance(active_tools, list):
                return jsonify({'error': 'active_tools must be null or an array'}), 400
            
            if isinstance(active_tools, list):
                # リスト内の要素が全て文字列かチェック
                if not all(isinstance(t, str) for t in active_tools):
                    return jsonify({'error': 'active_tools must contain only strings'}), 400
                
                # 存在するツール名かチェック（オプション）
                if ai_manager and ai_manager.tool_loader:
                    valid_tools = set(ai_manager.tool_loader.loaded_tools.keys())
                    invalid_tools = [t for t in active_tools if t not in valid_tools]
                    if invalid_tools:
                        return jsonify({
                            'error': f'Invalid tool names: {invalid_tools}',
                            'valid_tools': list(valid_tools)
                        }), 400
            
            # メタデータを更新
            chat_manager.update_chat_metadata(chat_id, {'active_tools': active_tools})
            
            return jsonify({
                'success': True,
                'active_tools': active_tools
            }), 200
            
        except FileNotFoundError:
            return jsonify({'error': 'Chat not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/send_message', methods=['POST'])
def send_message_and_get_response(chat_id):
    if not message_handler:
        return jsonify({'error': 'Message handler not initialized'}), 500
    
    payload = request.json
    user_message = payload.get('message')
    if not user_message:
        return jsonify({'error': 'Invalid request'}), 400
    
    try:
        result = message_handler.process_message(chat_id, payload)
        return jsonify(result)
    except Exception as e:
        import traceback
        print(f"APIリクエスト処理中にエラーが発生しました: {e}")
        traceback.print_exc()
        
        error_str = str(e)
        if "503" in error_str:
            return jsonify({
                'error': 'サーバーエラーが発生しました。自動的にリトライを試みましたが、問題が解決しませんでした。しばらく待ってから再度お試しください。',
                'retry_attempted': True
            }), 503
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/send_message_stream', methods=['POST'])
def send_message_and_get_response_stream(chat_id):
    """ストリーミング版のメッセージ送信エンドポイント"""
    if not message_handler:
        return jsonify({'error': 'Message handler not initialized'}), 500
    
    payload = request.json
    user_message = payload.get('message')
    if not user_message:
        return jsonify({'error': 'Invalid request'}), 400
    
    # ストリーミングフラグを追加
    payload['streaming'] = True
    
    try:
        # message_handlerがResponseオブジェクトを返すように変更済み
        return message_handler.process_message(chat_id, payload)
    except Exception as e:
        import traceback
        print(f"ストリーミングAPIリクエスト処理中にエラーが発生しました: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream/abort', methods=['POST'])
def abort_stream():
    """現在のストリーミングを強制停止"""
    try:
        if message_handler:
            message_handler.abort_current_stream()
        
        return jsonify({'success': True, 'message': 'Stream aborted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/add_system_message', methods=['POST'])
def add_system_message(chat_id):
    """システムメッセージ（強制停止など）を履歴に追加"""
    try:
        data = request.json
        
        # 履歴を読み込み
        chat_data = chat_manager.load_chat_history(chat_id)
        
        # システムメッセージを追加
        system_message = {
            'type': 'system',
            'event': data.get('event', 'unknown'),
            'text': data.get('text', ''),
            'timestamp': data.get('timestamp', time.time())
        }
        
        chat_data['messages'].append(system_message)
        
        # 保存
        chat_manager.save_chat_history(chat_id, chat_data)
        
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/continue', methods=['POST'])
def continue_message(chat_id):
    """中断されたメッセージの続きを生成"""
    if not message_handler:
        return jsonify({'error': 'Message handler not initialized'}), 500
    
    try:
        payload = request.json
        
        # 続きを要求するメッセージを作成
        continue_message_obj = {
            'type': 'user',
            'text': '続けてください',
            'files': []
        }
        
        # ペイロードを準備
        continue_payload = {
            'message': continue_message_obj,
            'model': payload.get('model', 'gemini-2.5-flash'),
            'thinking_budget': payload.get('thinking_budget', 0),
            'prompt': payload.get('prompt', 'normal_prompt'),
            'streaming': payload.get('streaming', False),
            'is_continuation': True
        }
        
        # ストリーミングモードの場合は特別な処理
        if continue_payload['streaming']:
            return message_handler.process_message(chat_id, continue_payload)
        else:
            result = message_handler.process_message(chat_id, continue_payload)
            return jsonify(result)
        
    except Exception as e:
        print(f"Continue endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/copy', methods=['POST'])
def copy_chat(chat_id):
    try:
        new_chat_id = chat_manager.copy_chat(chat_id)
        return jsonify({'success': True, 'new_chat_id': new_chat_id}), 201
    except FileNotFoundError:
        return jsonify({'error': 'Source chat not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# UI履歴関連のエンドポイント
@app.route('/api/chats/<chat_id>/ui_history', methods=['GET'])
def get_ui_history(chat_id):
    """UI履歴を取得"""
    try:
        ui_data = chat_manager.load_ui_history(chat_id)
        return jsonify(ui_data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/ui_history/logs', methods=['GET'])
def get_ui_history_logs(chat_id):
    """ツールログのみを取得"""
    try:
        ui_data = chat_manager.load_ui_history(chat_id)
        
        # クエリパラメータで実行IDによるフィルタリング
        execution_id = request.args.get('execution_id')
        if execution_id:
            logs = chat_manager.get_tool_logs_for_execution(chat_id, execution_id)
        else:
            logs = ui_data.get('tool_logs', [])
        
        return jsonify({'logs': logs}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/ui_history/append_log', methods=['POST'])
def append_ui_log(chat_id):
    """ツールログを追加（フロントエンドから直接追加する場合用）"""
    try:
        log_entry = request.json
        message_id = chat_manager.append_tool_log(chat_id, log_entry)
        return jsonify({'success': True, 'message_id': message_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/ui_history/state', methods=['GET', 'POST'])
def handle_ui_state(chat_id):
    """UI状態を取得/更新"""
    try:
        if request.method == 'GET':
            ui_data = chat_manager.load_ui_history(chat_id)
            return jsonify({'ui_state': ui_data.get('ui_state', {})}), 200
        
        elif request.method == 'POST':
            state_updates = request.json
            for key, value in state_updates.items():
                chat_manager.update_ui_state(chat_id, key, value)
            return jsonify({'success': True}), 200
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/<chat_id>/ui_history/clear', methods=['DELETE'])
def clear_ui_history(chat_id):
    """UI履歴をクリア"""
    try:
        chat_manager.clear_ui_history(chat_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ツール関連のエンドポイント
@app.route('/api/tools/messages', methods=['GET'])
def get_tool_messages():
    """ツールからのリアルタイムメッセージを取得"""
    messages = ai_manager.tool_loader.get_tool_messages() if ai_manager else []
    return jsonify(messages)

@app.route('/api/tools/messages/stream', methods=['GET'])
def stream_tool_messages():
    """ツールメッセージをSSE（Server-Sent Events）でストリーミング"""
    def generate():
        while True:
            messages = ai_manager.tool_loader.get_tool_messages() if ai_manager else []
            for msg in messages:
                yield f"data: {json.dumps(msg)}\n\n"
            time.sleep(0.1)  # 100msごとにチェック
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/tools/ui/<tool_name>', methods=['GET'])
def get_tool_ui_info(tool_name):
    """特定のツールのUI情報を取得"""
    if not ai_manager or tool_name not in ai_manager.tool_loader.loaded_tools:
        return jsonify({'error': 'Tool not found'}), 404
    
    tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
    
    return jsonify({
        'has_ui': tool_info.get('has_ui', False),
        'html_file': tool_info.get('html_file', 'index.html'),
        'icon': tool_info.get('icon', ''),
        'name': tool_info.get('name', '')
    })

@app.route('/api/tools/<tool_name>/start_ui', methods=['POST'])
def start_tool_ui(tool_name):
    """ツールのUIサーバーを起動"""
    if not ai_manager or tool_name not in ai_manager.tool_loader.loaded_tools:
        return jsonify({'error': 'Tool not found'}), 404
    
    tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
    module = tool_info.get('module')
    
    # ツールにstart_ui_server関数があれば呼び出し
    if hasattr(module, 'start_ui_server'):
        ui_port = module.start_ui_server()
        if ui_port:
            return jsonify({
                'success': True,
                'ui_port': ui_port,
                'html_file': tool_info.get('html_file', 'index.html')
            })
    
    return jsonify({'error': 'Tool does not support UI'}), 400

@app.route('/api/tools/reload', methods=['POST'])
def reload_tools():
    """ツールを再読み込みする"""
    try:
        result = ai_manager.tool_loader.reload_all_tools() if ai_manager else {'success': False, 'error': 'AI manager not initialized'}
        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tools/settings', methods=['GET'])
def get_tools_settings():
    """すべてのツールと設定を取得"""
    tools_data = ai_manager.tool_loader.get_all_tools_with_settings() if ai_manager else {}
    return jsonify(tools_data)

@app.route('/api/tools/settings/<tool_name>', methods=['POST'])
def update_tool_settings(tool_name):
    """特定のツールの設定を更新"""
    if not ai_manager:
        return jsonify({'success': False, 'error': 'AI manager not initialized'}), 500
    
    settings = request.json
    success = ai_manager.tool_loader.update_tool_settings(tool_name, settings)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to update settings"}), 500

@app.route('/api/tools/settings/<tool_name>', methods=['DELETE'])
def delete_tool_settings(tool_name):
    """特定のツールの設定を削除（設定のリセット）"""
    if not ai_manager:
        return jsonify({'success': False, 'error': 'AI manager not initialized'}), 500
    
    if tool_name in ai_manager.tool_loader.tool_settings:
        del ai_manager.tool_loader.tool_settings[tool_name]
        ai_manager.tool_loader._save_settings()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Tool settings not found"}), 404

@app.route('/api/tools/<tool_name>/venv-status', methods=['GET'])
def get_tool_venv_status(tool_name):
    """特定のツールの仮想環境ステータスを取得"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    tool_info = ai_manager.tool_loader.loaded_tools.get(tool_name)
    if not tool_info:
        return jsonify({'error': 'Tool not found'}), 404
    
    tool_dir = Path(tool_info['tool_dir'])
    venv_dir = tool_dir / ".venv"
    requirements_file = tool_dir / "requirements.txt"
    
    status = {
        'has_requirements': requirements_file.exists(),
        'has_venv': venv_dir.exists(),
        'venv_python': tool_info.get('venv_python'),
        'packages': []
    }
    
    # インストール済みパッケージを取得
    if status['has_venv'] and tool_info.get('venv_python'):
        try:
            result = subprocess.run(
                [tool_info['venv_python'], "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                import json
                status['packages'] = json.loads(result.stdout)
        except:
            pass
    
    return jsonify(status)

@app.route('/api/tools/debug', methods=['GET'])
def debug_tools():
    """ツールのデバッグ情報を取得"""
    if not ai_manager:
        return jsonify({
            'total_tools': 0,
            'tools': {},
            'duplicates': {},
            'has_duplicates': False
        }), 200
    
    tools_info = {}
    
    for tool_name, tool_data in ai_manager.tool_loader.loaded_tools.items():
        tools_info[tool_name] = {
            "display_name": tool_data["name"],
            "function_name": tool_data["function_declaration"]["name"],
            "file_path": tool_data["file_path"],
            "tool_dir": tool_data["tool_dir"]
        }
    
    # 重複チェック
    function_names = {}
    for tool_name, info in tools_info.items():
        func_name = info["function_name"]
        if func_name not in function_names:
            function_names[func_name] = []
        function_names[func_name].append(info)
    
    duplicates = {k: v for k, v in function_names.items() if len(v) > 1}
    
    return jsonify({
        "total_tools": len(tools_info),
        "tools": tools_info,
        "duplicates": duplicates,
        "has_duplicates": len(duplicates) > 0
    })

# テストエンドポイント
@app.route('/api/test/tool_execution')
def test_tool_execution():
    """ツール実行のテスト"""
    try:
        # 直接tool_loaderをテスト
        if ai_manager and ai_manager.tool_loader:
            test_context = {
                'chat_id': 'test-chat',
                'execution_id': 'test-exec',
                'chat_manager': chat_manager
            }
            
            # web_searchツールが存在するか確認
            if 'web_search' in ai_manager.tool_loader.loaded_tools:
                result = ai_manager.tool_loader.execute_tool(
                    'web_search',
                    {'query': 'test'},
                    test_context
                )
                return jsonify({'success': True, 'result': str(result)})
            else:
                return jsonify({'error': 'web_search tool not found'})
        else:
            return jsonify({'error': 'AI manager or tool loader not initialized'})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()})

# ツールUIサーバー関連のエンドポイント
@app.route('/api/tools/ui/status', methods=['GET'])
def get_ui_servers_status():
    """アクティブなUIサーバーの状態を取得"""
    active_servers = tool_ui_manager.get_active_servers()
    return jsonify({
        'active_count': len(active_servers),
        'servers': active_servers
    })

@app.route('/api/tools/<tool_name>/ui/start', methods=['POST'])
def start_tool_ui_server(tool_name):
    """特定のツールのUIサーバーを手動で起動"""
    if not ai_manager or tool_name not in ai_manager.tool_loader.loaded_tools:
        return jsonify({'error': 'Tool not found'}), 404
    
    tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
    ui_info = tool_ui_manager.start_tool_ui(tool_name, tool_info)
    
    if ui_info:
        return jsonify(ui_info), 200
    else:
        return jsonify({'error': 'Failed to start UI server'}), 500

@app.route('/api/tools/<tool_name>/ui/stop', methods=['POST'])
def stop_tool_ui_server(tool_name):
    """特定のツールのUIサーバーを停止"""
    success = tool_ui_manager.stop_tool_ui(tool_name)
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Server not found or failed to stop'}), 404

# ツールUI配信ルート
@app.route('/tools/<tool_name>/')
@app.route('/tools/<tool_name>/<path:filename>')
def serve_tool_ui(tool_name, filename='index.html'):
    """ツールのUIファイルを配信"""
    tool_path = Path('tool') / tool_name
    
    # セキュリティチェック
    if not tool_path.exists() or not tool_path.is_dir():
        abort(404, f"Tool '{tool_name}' not found")
    
    # HTMLファイルのパスを確認
    file_path = tool_path / filename
    
    # ファイルが存在しない場合、index.htmlを試す
    if not file_path.exists() and filename != 'index.html':
        file_path = tool_path / 'index.html'
    
    if not file_path.exists():
        abort(404, f"File '{filename}' not found in tool '{tool_name}'")
    
    # MIMEタイプを判定
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    # HTMLファイルの場合、動的にツールデータを注入
    if mime_type == 'text/html' or filename.endswith('.html'):
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # ツールのステータスやデータを注入
        tool_data = {
            'tool_name': tool_name,
            'tool_status': 'ready',
            'websocket_url': f'ws://localhost:5000/tools/{tool_name}/ws',
            'api_url': f'/api/tools/{tool_name}'
        }
        
        # HTMLに埋め込むスクリプトを追加
        inject_script = f"""
        <script>
            window.TOOL_CONFIG = {json.dumps(tool_data)};
        </script>
        """
        
        # </head>タグの前にスクリプトを注入
        if '</head>' in html_content:
            html_content = html_content.replace('</head>', inject_script + '</head>')
        else:
            html_content = inject_script + html_content
        
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
    
    # その他のファイル（CSS、JS、画像など）はそのまま配信
    return send_from_directory(str(tool_path), filename)

@app.route('/api/tools/<tool_name>/data', methods=['GET', 'POST'])
def tool_data_api(tool_name):
    """ツール固有のデータAPI"""
    if request.method == 'GET':
        # ツールのデータを取得
        tool_data = get_tool_data(tool_name)
        return jsonify(tool_data)
    
    elif request.method == 'POST':
        # ツールにデータを送信
        data = request.json
        result = send_data_to_tool(tool_name, data)
        return jsonify(result)

def get_tool_data(tool_name):
    """ツールのデータを取得"""
    # ツールローダーから情報を取得
    if ai_manager and tool_name in ai_manager.tool_loader.loaded_tools:
        tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
        
        # ツール固有のデータストアがあれば取得
        tool_data_store = getattr(tool_info.get('module'), 'ui_data', {})
        
        return {
            'name': tool_info['name'],
            'description': tool_info['description'],
            'icon': tool_info['icon'],
            'data': tool_data_store,
            'status': 'loaded'
        }
    
    return {'status': 'not_loaded', 'error': f'Tool {tool_name} not found'}

def send_data_to_tool(tool_name, data):
    """ツールにデータを送信"""
    if ai_manager and tool_name in ai_manager.tool_loader.loaded_tools:
        tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
        module = tool_info.get('module')
        
        # ツールにui_update関数があれば呼び出し
        if hasattr(module, 'ui_update'):
            result = module.ui_update(data)
            return {'success': True, 'result': result}
    
    return {'success': False, 'error': f'Tool {tool_name} not found or does not support UI updates'}

# WebSocket対応（オプション - flask-sockが必要）
try:
    from flask_sock import Sock
    sock = Sock(app)
    
    @sock.route('/tools/<tool_name>/ws')
    def tool_websocket(ws, tool_name):
        """ツール用WebSocket接続"""
        if ai_manager and tool_name in ai_manager.tool_loader.loaded_tools:
            tool_info = ai_manager.tool_loader.loaded_tools[tool_name]
            module = tool_info.get('module')
            
            # ツールにwebsocket_handler関数があれば呼び出し
            if hasattr(module, 'websocket_handler'):
                module.websocket_handler(ws)
            else:
                # デフォルトのエコーハンドラー
                while True:
                    message = ws.receive()
                    if message:
                        ws.send(f"Echo from {tool_name}: {message}")
                    else:
                        break
except ImportError:
    print("flask-sock not installed. WebSocket support disabled.")

# --- サポーター管理API ---

@app.route('/api/supporters', methods=['GET'])
def get_all_supporters():
    """利用可能なすべてのサポーターを取得"""
    if not supporter_loader:
        return jsonify({'error': 'Supporter loader not initialized'}), 500
    
    supporters = supporter_loader.get_all_supporters_info()
    return jsonify({
        'success': True,
        'supporters': supporters,
        'count': len(supporters)
    })


@app.route('/api/supporters/reload', methods=['POST'])
def reload_supporters():
    """サポーターを再読み込み"""
    if not supporter_loader:
        return jsonify({'error': 'Supporter loader not initialized'}), 500
    
    result = supporter_loader.reload_all_supporters()
    return jsonify(result)


@app.route('/api/supporters/<supporter_name>/settings', methods=['GET', 'POST'])
def handle_supporter_settings(supporter_name):
    """サポーターの設定を取得/更新"""
    if not supporter_loader:
        return jsonify({'error': 'Supporter loader not initialized'}), 500
    
    if request.method == 'GET':
        settings = supporter_loader.get_supporter_settings(supporter_name)
        return jsonify(settings)
    
    elif request.method == 'POST':
        success = supporter_loader.update_supporter_settings(supporter_name, request.json)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to update settings'}), 500


@app.route('/api/supporters/<supporter_name>/venv-status', methods=['GET'])
def get_supporter_venv_status(supporter_name):
    """サポーターの仮想環境ステータスを取得"""
    if not supporter_dependency_manager:
        return jsonify({'error': 'Dependency manager not initialized'}), 500
    
    status = supporter_dependency_manager.get_venv_status(supporter_name)
    return jsonify(status)


@app.route('/api/supporters/<supporter_name>/install-deps', methods=['POST'])
def install_supporter_dependencies(supporter_name):
    """サポーターの依存関係をインストール"""
    if not supporter_dependency_manager:
        return jsonify({'error': 'Dependency manager not initialized'}), 500
    
    result = supporter_dependency_manager.install_requirements(supporter_name)
    return jsonify(result)


@app.route('/api/chats/<chat_id>/supporters', methods=['GET', 'POST'])
def handle_chat_supporters(chat_id):
    """チャットごとのサポーター設定を取得/更新"""
    
    if request.method == 'GET':
        try:
            # チャット履歴を読み込んで active_supporters を取得
            chat_data = chat_manager.load_chat_history(chat_id)
            active_supporters = chat_data.get('active_supporters', [])
            
            # 全サポーター一覧を取得
            all_supporters = []
            if supporter_loader:
                all_supporters = supporter_loader.get_all_supporters_info()
            
            return jsonify({
                'active_supporters': active_supporters,
                'all_supporters': all_supporters
            }), 200
            
        except FileNotFoundError:
            return jsonify({'error': 'Chat not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.json
            
            if 'supporters' not in data:
                return jsonify({'error': 'supporters field is required'}), 400
            
            supporters_list = data['supporters']
            
            # バリデーション
            if not isinstance(supporters_list, list):
                return jsonify({'error': 'supporters must be an array'}), 400
            
            if not all(isinstance(s, str) for s in supporters_list):
                return jsonify({'error': 'supporters must contain only strings'}), 400
            
            # 存在するサポーター名かチェック（オプション）
            if supporter_loader:
                valid_supporters = set(supporter_loader.loaded_supporters.keys())
                invalid_supporters = [s for s in supporters_list if s not in valid_supporters]
                if invalid_supporters:
                    return jsonify({
                        'error': f'Invalid supporter names: {invalid_supporters}',
                        'valid_supporters': list(valid_supporters)
                    }), 400
            
            # メタデータを更新
            chat_manager.update_chat_metadata(chat_id, {'active_supporters': supporters_list})
            
            return jsonify({
                'success': True,
                'active_supporters': supporters_list
            }), 200
            
        except FileNotFoundError:
            return jsonify({'error': 'Chat not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# --- リレーションシップ管理API ---

@app.route('/api/relationships', methods=['GET', 'POST'])
def handle_relationships():
    """リレーションシップの取得/作成"""
    
    if request.method == 'GET':
        # クエリパラメータでフィルタリング
        entity_id = request.args.get('entity_id')
        link_type = request.args.get('type')
        direction = request.args.get('direction', 'both')
        
        if entity_id:
            links = relationship_manager.get_related(entity_id, link_type, direction)
        else:
            links = relationship_manager.get_all_links()
        
        return jsonify({'links': links}), 200
    
    elif request.method == 'POST':
        try:
            data = request.json
            
            required_fields = ['source', 'target', 'type']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'{field} is required'}), 400
            
            link = relationship_manager.link(
                source=data['source'],
                target=data['target'],
                link_type=data['type'],
                metadata=data.get('metadata', {})
            )
            
            return jsonify({'success': True, 'link': link}), 201
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/relationships/<entity_id>', methods=['GET', 'DELETE'])
def handle_entity_relationships(entity_id):
    """特定エンティティのリレーションシップを取得/削除"""
    
    if request.method == 'GET':
        link_type = request.args.get('type')
        direction = request.args.get('direction', 'both')
        
        links = relationship_manager.get_related(entity_id, link_type, direction)
        ids = relationship_manager.get_related_ids(entity_id, link_type, direction)
        
        return jsonify({
            'entity_id': entity_id,
            'links': links,
            'related_ids': ids
        }), 200
    
    elif request.method == 'DELETE':
        # 特定のリンクを削除
        data = request.json or {}
        target = data.get('target')
        link_type = data.get('type')
        
        if target and link_type:
            # 特定のリンクを削除
            success = relationship_manager.unlink(entity_id, target, link_type)
            return jsonify({'success': success}), 200 if success else 404
        else:
            # エンティティに関連する全リンクを削除
            count = relationship_manager.delete_all_links_for(entity_id)
            return jsonify({'success': True, 'deleted_count': count}), 200

# AIモデル関連のエンドポイント
@app.route('/api/ai/models', methods=['GET'])
def get_ai_models():
    """利用可能なAIモデルの一覧を取得"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    models = ai_manager.get_available_models()
    print(f"[DEBUG] 利用可能なモデル数: {len(models)}")
    for model in models:
        print(f"  - {model['id']}: {model['name']} ({model['provider']})")
    
    return jsonify({
        'success': True,
        'models': models,
        'count': len(models)
    })

@app.route('/api/ai/models/search', methods=['POST'])
def search_ai_models():
    """条件に基づいてAIモデルを検索"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    criteria = request.json or {}
    models = ai_manager.search_models(**criteria)
    
    print(f"[DEBUG] 検索条件: {criteria}")
    print(f"[DEBUG] 検索結果: {len(models)}件")
    
    return jsonify({
        'success': True,
        'models': models,
        'count': len(models)
    })

@app.route('/api/ai/test', methods=['GET'])
def test_ai_system():
    """AIシステムのテスト"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    test_results = {
        'ai_manager_initialized': True,
        'ai_loader_initialized': ai_manager.ai_loader is not None,
        'loaded_providers': list(ai_manager.ai_loader.loaded_clients.keys()),
        'total_models': len(ai_manager.ai_loader.model_profiles),
        'current_provider': ai_manager.current_provider,
        'current_model': ai_manager.current_model_id,
        'tool_loader_initialized': ai_manager.tool_loader is not None,
        'loaded_tools': len(ai_manager.tool_loader.loaded_tools) if ai_manager.tool_loader else 0
    }
    
    print("[DEBUG] AIシステムテスト結果:")
    for key, value in test_results.items():
        print(f"  {key}: {value}")
    
    return jsonify(test_results)

@app.route('/api/ai/favorites', methods=['GET'])
def get_favorite_models():
    """お気に入りモデルの一覧を取得"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    try:
        user_settings = settings_manager.get_user_settings()
        favorite_model_ids = user_settings.get('favorite_models', [])
        
        # モデルの詳細情報を取得
        favorite_models = []
        for model_id in favorite_model_ids:
            profile = ai_manager.ai_loader.get_model_profile(model_id)
            if profile:
                favorite_models.append({
                    'id': model_id,
                    'name': profile['basic_info']['name'],
                    'provider': profile['provider_name'],
                    'description': profile['basic_info'].get('description', ''),
                    'features': profile.get('features', {})
                })
        
        return jsonify({
            'success': True,
            'favorites': favorite_models
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/favorites', methods=['POST'])
def add_favorite_model():
    """お気に入りにモデルを追加"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    try:
        data = request.json
        model_id = data.get('model_id')
        
        if not model_id:
            return jsonify({'error': 'model_id is required'}), 400
        
        # モデルが存在するか確認
        profile = ai_manager.ai_loader.get_model_profile(model_id)
        if not profile:
            return jsonify({'error': 'Model not found'}), 404
        
        # 現在の設定を取得
        user_settings = settings_manager.get_user_settings()
        favorite_models = user_settings.get('favorite_models', [])
        
        # 重複チェック
        if model_id not in favorite_models:
            favorite_models.append(model_id)
            user_settings['favorite_models'] = favorite_models
            settings_manager.save_user_settings(user_settings)
        
        return jsonify({
            'success': True,
            'message': f'{model_id} をお気に入りに追加しました'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/favorites/<model_id>', methods=['DELETE'])
def remove_favorite_model(model_id):
    """お気に入りからモデルを削除"""
    try:
        user_settings = settings_manager.get_user_settings()
        favorite_models = user_settings.get('favorite_models', [])
        
        if model_id in favorite_models:
            favorite_models.remove(model_id)
            user_settings['favorite_models'] = favorite_models
            settings_manager.save_user_settings(user_settings)
        
        return jsonify({
            'success': True,
            'message': f'{model_id} をお気に入りから削除しました'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/set-model', methods=['POST'])
def set_current_model():
    """現在使用するモデルを設定"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    try:
        data = request.json
        model_id = data.get('model_id')
        
        if not model_id:
            return jsonify({'error': 'model_id is required'}), 400
        
        # モデルを設定
        success = ai_manager.set_model(model_id)
        
        if success:
            # ユーザー設定も更新
            user_settings = settings_manager.get_user_settings()
            user_settings['model'] = model_id
            settings_manager.save_user_settings(user_settings)
            
            return jsonify({
                'success': True,
                'message': f'モデルを {model_id} に設定しました'
            })
        else:
            return jsonify({'error': 'Failed to set model'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# デバッグログ関連のエンドポイント
@app.route('/api/debug/logging', methods=['POST'])
def set_debug_logging():
    """デバッグログの有効/無効を設定"""
    if not ai_manager:
        return jsonify({'error': 'AI manager not initialized'}), 500
    
    try:
        data = request.json
        enabled = data.get('enabled', False)
        ai_manager.set_debug_logging(enabled)
        
        return jsonify({
            'success': True,
            'enabled': enabled,
            'log_file': 'debug.txt'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- エコシステム管理API ---

@app.route('/api/ecosystem/status', methods=['GET'])
def get_ecosystem_status():
    """エコシステムのステータスを取得"""
    try:
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        from backend_core.ecosystem import get_registry, get_active_ecosystem_manager
        
        if not is_ecosystem_initialized():
            return jsonify({
                'initialized': False,
                'message': 'エコシステムは初期化されていません'
            })
        
        registry = get_registry()
        active_manager = get_active_ecosystem_manager()
        
        return jsonify({
            'initialized': True,
            'active_pack_identity': active_manager.active_pack_identity,
            'packs': list(registry.packs.keys()),
            'total_components': len(registry.get_all_components()),
            'overrides': active_manager.get_all_overrides()
        })
    except ImportError:
        return jsonify({
            'initialized': False,
            'message': 'エコシステムモジュールが利用できません'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ecosystem/packs', methods=['GET'])
def get_ecosystem_packs():
    """利用可能なPackの一覧を取得"""
    try:
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        from backend_core.ecosystem import get_registry
        
        if not is_ecosystem_initialized():
            return jsonify({'error': 'Ecosystem not initialized'}), 500
        
        registry = get_registry()
        packs = []
        
        for pack_id, pack_info in registry.packs.items():
            packs.append({
                'pack_id': pack_id,
                'pack_identity': pack_info.pack_identity,
                'version': pack_info.version,
                'uuid': pack_info.uuid,
                'components_count': len(pack_info.components),
                'addons_count': len(pack_info.addons)
            })
        
        return jsonify({
            'success': True,
            'packs': packs
        })
    except ImportError:
        return jsonify({'error': 'Ecosystem module not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ecosystem/components', methods=['GET'])
def get_ecosystem_components():
    """利用可能なComponentの一覧を取得"""
    try:
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        from backend_core.ecosystem import get_registry
        
        if not is_ecosystem_initialized():
            return jsonify({'error': 'Ecosystem not initialized'}), 500
        
        registry = get_registry()
        components = []
        
        for component in registry.get_all_components():
            components.append({
                'type': component.type,
                'id': component.id,
                'version': component.version,
                'uuid': component.uuid,
                'pack_id': component.pack_id,
                'full_id': component.full_id
            })
        
        return jsonify({
            'success': True,
            'components': components
        })
    except ImportError:
        return jsonify({'error': 'Ecosystem module not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ecosystem/addons', methods=['GET'])
def get_ecosystem_addons():
    """利用可能なAddonの一覧を取得"""
    try:
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        from backend_core.ecosystem import get_addon_manager
        
        if not is_ecosystem_initialized():
            return jsonify({'error': 'Ecosystem not initialized'}), 500
        
        addon_manager = get_addon_manager()
        addons = []
        
        for addon in addon_manager.get_all_addons():
            addons.append({
                'addon_id': addon.addon_id,
                'version': addon.version,
                'priority': addon.priority,
                'enabled': addon.enabled,
                'pack_id': addon.pack_id,
                'full_id': addon.full_id
            })
        
        return jsonify({
            'success': True,
            'addons': addons
        })
    except ImportError:
        return jsonify({'error': 'Ecosystem module not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ecosystem/overrides', methods=['GET', 'POST'])
def handle_ecosystem_overrides():
    """コンポーネントオーバーライドの取得/設定"""
    try:
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        from backend_core.ecosystem import get_active_ecosystem_manager
        
        if not is_ecosystem_initialized():
            return jsonify({'error': 'Ecosystem not initialized'}), 500
        
        manager = get_active_ecosystem_manager()
        
        if request.method == 'GET':
            return jsonify({
                'success': True,
                'overrides': manager.get_all_overrides()
            })
        
        elif request.method == 'POST':
            data = request.json
            component_type = data.get('component_type')
            component_id = data.get('component_id')
            
            if not component_type or not component_id:
                return jsonify({'error': 'component_type and component_id are required'}), 400
            
            manager.set_override(component_type, component_id)
            
            return jsonify({
                'success': True,
                'message': f'{component_type} を {component_id} に設定しました'
            })
    except ImportError:
        return jsonify({'error': 'Ecosystem module not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ecosystem/reload', methods=['POST'])
def reload_ecosystem():
    """エコシステムを再読み込み"""
    try:
        from backend_core.ecosystem import reload_registry, reload_addon_manager
        from backend_core.ecosystem.compat import is_ecosystem_initialized
        
        if not is_ecosystem_initialized():
            return jsonify({'error': 'Ecosystem not initialized'}), 500
        
        registry = reload_registry()
        addon_manager = reload_addon_manager()
        
        # アドオンを再読み込み
        for pack in registry.packs.values():
            addon_manager.load_addons_from_pack(pack)
        
        return jsonify({
            'success': True,
            'packs_loaded': len(registry.packs),
            'components_loaded': len(registry.get_all_components()),
            'addons_loaded': len(addon_manager.get_all_addons())
        })
    except ImportError:
        return jsonify({'error': 'Ecosystem module not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# アプリケーション終了時のクリーンアップ
import atexit

def cleanup():
    """アプリケーション終了時のクリーンアップ"""
    print("Cleaning up UI servers...")
    tool_ui_manager.stop_all_ui_servers()

atexit.register(cleanup)

if __name__ == '__main__':
    # デバッグログ設定を適用
    if ai_manager:
        settings = settings_manager.get_user_settings()
        if settings.get('debug_logging', False):
            ai_manager.set_debug_logging(True)
    
    app.run(debug=True, port=5000)
