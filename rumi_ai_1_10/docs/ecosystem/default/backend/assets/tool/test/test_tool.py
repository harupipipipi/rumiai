"""
テストツール
実行時に渡された全ての情報を詳細に出力します
"""

import json
import os
from pathlib import Path
from flask import Flask, render_template_string, jsonify
import threading
from datetime import datetime

TOOL_NAME = "情報テストツール"
TOOL_DESCRIPTION = "実行時に渡された全ての情報（コンテキスト、引数、設定）を詳細に表示します"
TOOL_ICON = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>'

# UIサーバーの状態を保持
ui_app = None
ui_thread = None
latest_execution_data = {}

def get_function_declaration():
    """Gemini Function Calling用の関数定義を返す"""
    return {
        "name": "test_info",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "required": ["test_input"],
            "properties": {
                "test_input": {
                    "type": "string",
                    "description": "テスト用の入力文字列"
                },
                "optional_number": {
                    "type": "number",
                    "description": "オプションの数値パラメータ"
                },
                "optional_boolean": {
                    "type": "boolean",
                    "description": "オプションの真偽値パラメータ"
                }
            }
        }
    }

def get_settings_schema():
    """設定項目のスキーマを返す"""
    return {
        "verbose_mode": {
            "type": "boolean",
            "label": "詳細モード",
            "description": "より詳細な情報を出力します",
            "default": True
        },
        "output_format": {
            "type": "select",
            "label": "出力フォーマット",
            "description": "結果の出力形式を選択",
            "default": "json",
            "options": [
                {"value": "json", "label": "JSON形式"},
                {"value": "text", "label": "テキスト形式"},
                {"value": "markdown", "label": "Markdown形式"}
            ]
        },
        "save_to_file": {
            "type": "boolean",
            "label": "ファイルに保存",
            "description": "実行結果をファイルに保存します",
            "default": False
        },
        "test_api_key": {
            "type": "text",
            "label": "テストAPIキー",
            "description": "設定値のテスト用",
            "placeholder": "test-api-key-here",
            "default": ""
        }
    }

def execute(args: dict, context: dict) -> dict:
    """
    ツールの実行
    
    Args:
        args: AIから渡された引数
        context: 実行コンテキスト
    """
    global latest_execution_data
    
    try:
        # 実行時刻
        execution_time = datetime.now().isoformat()
        
        # リアルタイムメッセージを送信
        context["message_callback"]("テストツールを実行中...")
        context["message_callback"](f"受信した引数: {json.dumps(args, ensure_ascii=False)}")
        
        # 設定を取得
        settings = context.get("settings", {})
        verbose_mode = settings.get("verbose_mode", True)
        output_format = settings.get("output_format", "json")
        save_to_file = settings.get("save_to_file", False)
        test_api_key = settings.get("test_api_key", "")
        
        # test.pngファイルのパスを構築
        tool_dir_path = Path(context.get("tool_dir", ""))
        test_png_path = tool_dir_path / "test.png"
        
        # test.pngの存在確認
        test_png_info = {
            "path": str(test_png_path),
            "exists": test_png_path.exists(),
            "is_file": test_png_path.is_file() if test_png_path.exists() else False,
            "size": test_png_path.stat().st_size if test_png_path.exists() else 0,
            "absolute_path": str(test_png_path.absolute())
        }
        
        context["message_callback"](f"test.pngを検索中: {test_png_path}")
        
        # 全情報を収集
        execution_info = {
            "execution_time": execution_time,
            "received_args": args,
            "test_png_info": test_png_info,  # test.png情報を追加
            "context_info": {
                "model": context.get("model", "不明"),
                "thinking_budget": context.get("thinking_budget", 0),
                "chat_path": context.get("chat_path", "不明"),
                "history_path": context.get("history_path", "不明"),
                "app_path": context.get("app_path", "不明"),
                "tool_dir": context.get("tool_dir", "不明"),
                "ui_port": context.get("ui_port", None),
                "main_port": context.get("main_port", "5000")
            },
            "settings": {
                "verbose_mode": verbose_mode,
                "output_format": output_format,
                "save_to_file": save_to_file,
                "test_api_key": "***" if test_api_key else "(未設定)",
                "test_api_key_length": len(test_api_key)
            },
            "environment": {
                "python_version": os.sys.version,
                "platform": os.sys.platform,
                "current_directory": os.getcwd(),
                "tool_directory": context.get("tool_dir", "不明")
            }
        }
        
        # パス情報の検証
        path_validations = {}
        for path_key in ["chat_path", "history_path", "app_path", "tool_dir"]:
            path_value = context.get(path_key, "")
            if path_value and path_value != "不明":
                path_obj = Path(path_value)
                path_validations[path_key] = {
                    "value": str(path_value),
                    "exists": path_obj.exists(),
                    "is_file": path_obj.is_file() if path_obj.exists() else None,
                    "is_dir": path_obj.is_dir() if path_obj.exists() else None,
                    "absolute": str(path_obj.absolute())
                }
        execution_info["path_validations"] = path_validations
        
        # 最新の実行データを保存（UI表示用）
        latest_execution_data = execution_info
        
        # UIがある場合は起動
        if context.get("ui_port"):
            context["message_callback"](f"UIサーバーをポート {context['ui_port']} で起動中...")
            start_ui_server(context["ui_port"], context["tool_dir"], execution_info)
        
        # 結果のフォーマット
        if output_format == "json":
            result_text = json.dumps(execution_info, ensure_ascii=False, indent=2)
        elif output_format == "markdown":
            result_text = format_as_markdown(execution_info)
        else:  # text
            result_text = format_as_text(execution_info)
        
        # ファイルに保存（オプション）
        saved_file = None
        if save_to_file:
            saved_file = save_execution_info(execution_info, context.get("tool_dir", "."))
            context["message_callback"](f"実行情報をファイルに保存: {saved_file}")
        
        # 詳細モードでない場合は簡潔な結果を返す
        if not verbose_mode:
            result_text = f"テスト実行完了\n入力: {args.get('test_input')}\n実行時刻: {execution_time}"
            if test_png_info["exists"]:
                result_text += f"\ntest.png: 見つかりました（{test_png_info['size']}バイト）"
            else:
                result_text += "\ntest.png: 見つかりませんでした"
        
        context["message_callback"]("テストツールの実行が完了しました")
        
        # 成功時の応答
        response = {
            "success": True,
            "result": result_text,
            "execution_time": execution_time,
            "received_args": args,
            "model_used": context.get("model", "不明"),
            "thinking_budget": context.get("thinking_budget", 0),
            "test_png_found": test_png_info["exists"],
            "test_png_size": test_png_info["size"] if test_png_info["exists"] else 0
        }
        
        # test.pngが存在する場合、ファイルとして添付
        files_to_attach = []
        if test_png_info["exists"]:
            context["message_callback"](f"test.pngを添付ファイルとして追加します")
            
            # test.pngをbase64エンコードして添付
            import base64
            with open(test_png_path, 'rb') as f:
                png_data = f.read()
                png_base64 = base64.b64encode(png_data).decode('utf-8')
                files_to_attach.append({
                    "path": f"data:image/png;base64,{png_base64}",
                    "type": "image/png",
                    "name": "test.png",
                    "size": test_png_info["size"]
                })
        
        # 保存したJSONファイルも添付
        if saved_file:
            files_to_attach.append({
                "path": saved_file,
                "type": "application/json",
                "name": os.path.basename(saved_file)
            })
        
        if files_to_attach:
            response["files"] = files_to_attach
        
        return response
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        context["message_callback"](f"エラーが発生しました: {str(e)}")
        
        return {
            "success": False,
            "error": str(e),
            "error_details": error_details,
            "received_args": args,
            "context_keys": list(context.keys())
        }

def format_as_markdown(info: dict) -> str:
    """情報をMarkdown形式でフォーマット"""
    md = "# テストツール実行結果\n\n"
    md += f"## 実行時刻\n{info['execution_time']}\n\n"
    
    # test.png情報を追加
    md += "## test.png情報\n"
    png_info = info.get('test_png_info', {})
    if png_info.get('exists'):
        md += f"✅ **ファイルが見つかりました**\n"
        md += f"- サイズ: {png_info.get('size', 0)} バイト\n"
        md += f"- パス: `{png_info.get('absolute_path', '')}`\n\n"
    else:
        md += "❌ **ファイルが見つかりませんでした**\n"
        md += f"- 検索パス: `{png_info.get('absolute_path', '')}`\n\n"
    
    md += "## 受信した引数\n```json\n"
    md += json.dumps(info['received_args'], ensure_ascii=False, indent=2)
    md += "\n```\n\n"
    
    md += "## コンテキスト情報\n"
    for key, value in info['context_info'].items():
        md += f"- **{key}**: {value}\n"
    md += "\n"
    
    md += "## 設定値\n"
    for key, value in info['settings'].items():
        md += f"- **{key}**: {value}\n"
    md += "\n"
    
    md += "## パス検証結果\n"
    for path_key, validation in info.get('path_validations', {}).items():
        md += f"### {path_key}\n"
        md += f"- 存在: {validation['exists']}\n"
        md += f"- 絶対パス: `{validation['absolute']}`\n"
    
    return md

def format_as_text(info: dict) -> str:
    """情報をテキスト形式でフォーマット"""
    text = "=== テストツール実行結果 ===\n\n"
    text += f"実行時刻: {info['execution_time']}\n\n"
    
    # test.png情報を追加
    text += "【test.png情報】\n"
    png_info = info.get('test_png_info', {})
    if png_info.get('exists'):
        text += f"  状態: 見つかりました\n"
        text += f"  サイズ: {png_info.get('size', 0)} バイト\n"
        text += f"  パス: {png_info.get('absolute_path', '')}\n"
    else:
        text += f"  状態: 見つかりませんでした\n"
        text += f"  検索パス: {png_info.get('absolute_path', '')}\n"
    text += "\n"
    
    text += "【受信した引数】\n"
    for key, value in info['received_args'].items():
        text += f"  {key}: {value}\n"
    text += "\n"
    
    text += "【コンテキスト情報】\n"
    for key, value in info['context_info'].items():
        text += f"  {key}: {value}\n"
    text += "\n"
    
    text += "【設定値】\n"
    for key, value in info['settings'].items():
        text += f"  {key}: {value}\n"
    
    return text

def save_execution_info(info: dict, tool_dir: str) -> str:
    """実行情報をファイルに保存"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_execution_{timestamp}.json"
    filepath = Path(tool_dir) / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    
    return str(filepath)

def start_ui_server(port: int, tool_dir: str, execution_info: dict):
    """UIサーバーを起動"""
    global ui_app, ui_thread
    
    if ui_app is None:
        ui_app = Flask(__name__)
        
        @ui_app.route('/')
        def index():
            # カスタムHTMLを生成
            html_content = generate_ui_html(execution_info)
            return render_template_string(html_content)
        
        @ui_app.route('/api/latest')
        def get_latest():
            return jsonify(latest_execution_data)
        
        # バックグラウンドで起動
        ui_thread = threading.Thread(
            target=lambda: ui_app.run(port=port, debug=False, use_reloader=False),
            daemon=True
        )
        ui_thread.start()

def generate_ui_html(info: dict) -> str:
    """UI用のHTMLを生成"""
    png_info = info.get('test_png_info', {})
    png_status_html = ""
    
    if png_info.get('exists'):
        png_status_html = f'''
        <div class="bg-green-50 border-l-4 border-green-500 p-4">
            <div class="flex items-center">
                <svg class="w-6 h-6 text-green-500 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                </svg>
                <div>
                    <p class="font-semibold text-green-700">test.pngが見つかりました</p>
                    <p class="text-sm text-green-600">サイズ: {png_info.get('size', 0)} バイト</p>
                </div>
            </div>
        </div>
        '''
    else:
        png_status_html = f'''
        <div class="bg-red-50 border-l-4 border-red-500 p-4">
            <div class="flex items-center">
                <svg class="w-6 h-6 text-red-500 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
                <div>
                    <p class="font-semibold text-red-700">test.pngが見つかりませんでした</p>
                    <p class="text-sm text-red-600">検索パス: {png_info.get('absolute_path', '')}</p>
                </div>
            </div>
        </div>
        '''
    
    return '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>テストツール実行情報</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 p-4">
    <div class="max-w-4xl mx-auto">
        <h1 class="text-2xl font-bold mb-4 text-gray-800">🔍 テストツール実行情報</h1>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-4">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">test.png ステータス</h2>
            ''' + png_status_html + '''
        </div>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-4">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">実行時刻</h2>
            <p class="text-gray-700">''' + info.get('execution_time', '不明') + '''</p>
        </div>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-4">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">受信した引数</h2>
            <pre class="bg-gray-50 p-3 rounded overflow-x-auto text-sm">''' + json.dumps(info.get('received_args', {}), ensure_ascii=False, indent=2) + '''</pre>
        </div>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-4">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">コンテキスト情報</h2>
            <div class="space-y-2">
                ''' + '\n'.join([f'<div class="flex"><span class="font-medium w-40">{k}:</span><span class="text-gray-700">{v}</span></div>' 
                                for k, v in info.get('context_info', {}).items()]) + '''
            </div>
        </div>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-4">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">設定値</h2>
            <div class="space-y-2">
                ''' + '\n'.join([f'<div class="flex"><span class="font-medium w-40">{k}:</span><span class="text-gray-700">{v}</span></div>' 
                                for k, v in info.get('settings', {}).items()]) + '''
            </div>
        </div>
        
        <div class="bg-white rounded-lg shadow-md p-6">
            <h2 class="text-lg font-semibold mb-3 text-blue-600">パス検証結果</h2>
            <div class="space-y-3">
                ''' + '\n'.join([f'''
                <div class="border-l-4 border-{"green" if v.get("exists") else "red"}-500 pl-3">
                    <div class="font-medium">{k}</div>
                    <div class="text-sm text-gray-600">存在: {v.get("exists")}</div>
                    <div class="text-xs text-gray-500 break-all">{v.get("absolute")}</div>
                </div>''' for k, v in info.get('path_validations', {}).items()]) + '''
            </div>
        </div>
        
        <div class="mt-4 text-center">
            <button onclick="location.reload()" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                更新
            </button>
        </div>
    </div>
    
    <script>
        // 自動更新（5秒ごと）
        setInterval(async () => {
            try {
                const response = await fetch('/api/latest');
                const data = await response.json();
                console.log('Latest execution data:', data);
            } catch (error) {
                console.error('Failed to fetch latest data:', error);
            }
        }, 5000);
    </script>
</body>
</html>
    '''
