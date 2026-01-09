"""
ツールテンプレート - ファイル返却の例を含む
このファイルをコピーして新しいツールを作成してください
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template_string
import threading

TOOL_NAME = "サンプルツール"
TOOL_DESCRIPTION = "サンプルツールの説明"
TOOL_ICON = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a8 8 0 100 16 8 8 0 000-16z"></path></svg>'

def get_function_declaration():
    """Gemini Function Calling用の関数定義を返す"""
    return {
        "name": "sample_tool",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "required": ["input_text"],
            "properties": {
                "input_text": {
                    "type": "string",
                    "description": "入力テキスト"
                }
            }
        }
    }

def get_settings_schema():
    """設定項目のスキーマを返す（オプション）"""
    return {
        "api_key": {
            "type": "text",
            "label": "APIキー",
            "description": "外部APIのアクセスキー",
            "placeholder": "your-api-key-here",
            "default": ""
        },
        "enable_cache": {
            "type": "boolean",
            "label": "キャッシュを有効化",
            "description": "結果をキャッシュして高速化します",
            "default": True
        },
        "timeout": {
            "type": "number",
            "label": "タイムアウト（秒）",
            "description": "処理のタイムアウト時間",
            "default": 30,
            "min": 1,
            "max": 300,
            "step": 1
        },
        "mode": {
            "type": "select",
            "label": "動作モード",
            "description": "ツールの動作モードを選択",
            "default": "standard",
            "options": [
                {"value": "standard", "label": "標準"},
                {"value": "advanced", "label": "高度"},
                {"value": "debug", "label": "デバッグ"}
            ]
        }
    }

def execute(args: dict, context: dict) -> dict:
    """
    ツールの実行
    
    Args:
        args: AIから渡された引数
        context: 実行コンテキスト
            - model: 使用中のAIモデル
            - thinking_budget: 思考予算
            - chat_path: チャットディレクトリのパス
            - history_path: history.jsonのパス
            - app_path: app.pyのパス
            - tool_dir: このツールのディレクトリ
            - ui_port: UI用のポート（UIがある場合）
            - settings: ツールの設定値
            - has_venv: 専用仮想環境の有無
            - venv_python: 専用仮想環境のPythonパス
            - message_callback: リアルタイムメッセージ送信用
    
    ファイルをAIに渡す例：
    1. ファイルを生成または取得
    2. result["files"]にファイル情報を追加
    3. AIがファイルを認識して処理
    """
    try:
        # 設定を取得
        settings = context.get("settings", {})
        api_key = settings.get("api_key", "")
        enable_cache = settings.get("enable_cache", True)
        timeout = settings.get("timeout", 30)
        mode = settings.get("mode", "standard")
        
        # リアルタイムメッセージを送信
        context["message_callback"](f"処理を開始しています（モード: {mode}）")
        context["message_callback"](f"入力テキスト: {args.get('input_text')}")
        
        # 設定に基づいて処理を実行
        if not api_key and mode != "debug":
            context["message_callback"]("APIキーが設定されていません")
            return {
                "success": False,
                "error": "APIキーが設定されていません。設定画面から設定してください。"
            }
        
        # ツールディレクトリのパス
        tool_dir = Path(context["tool_dir"])
        
        # 処理の進行状況を報告
        context["message_callback"]("ファイルを準備しています...")
        
        # 例1: 既存のファイルをAIに渡す
        files_to_return = []
        sample_image = tool_dir / "sample.png"
        
        if sample_image.exists():
            files_to_return.append({
                "path": str(sample_image),  # ファイルパス
                "type": "image/png",        # MIMEタイプ
                "description": "サンプル画像"  # 説明（オプション）
            })
            context["message_callback"](f"既存の画像ファイルを検出: {sample_image.name}")
        
        # 例2: 動的にファイルを生成してAIに渡す
        context["message_callback"]("テキストファイルを生成中...")
        output_file = tool_dir / "output.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"=== ツール実行レポート ===\n")
            f.write(f"実行時刻: {context.get('timestamp', 'N/A')}\n")
            f.write(f"使用モデル: {context.get('model', 'N/A')}\n")
            f.write(f"動作モード: {mode}\n")
            f.write(f"キャッシュ: {'有効' if enable_cache else '無効'}\n")
            f.write(f"タイムアウト: {timeout}秒\n")
            f.write(f"\n--- 入力内容 ---\n")
            f.write(f"入力テキスト: {args.get('input_text')}\n")
            f.write(f"\n--- 処理結果 ---\n")
            f.write(f"これはツールが生成したファイルです。\n")
            f.write(f"処理は正常に完了しました。\n")
        
        files_to_return.append({
            "path": str(output_file),
            "type": "text/plain",
            "description": "生成されたテキストファイル"
        })
        context["message_callback"](f"テキストファイルを生成しました: {output_file.name}")
        
        # 例3: 画像を生成してAIに渡す（PILを使用する例）
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            context["message_callback"]("画像を生成中...")
            
            # 簡単な画像を生成
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            
            # 背景にグラデーションを追加
            for i in range(200):
                color = (255 - i, 255 - i, 255)
                draw.rectangle([(0, i), (400, i+1)], fill=color)
            
            # テキストを描画
            text = args.get('input_text', 'Sample')
            # デフォルトフォントを使用
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
            except:
                font = None
            
            # テキストを中央に配置
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = (400 - text_width) // 2
            text_y = (200 - text_height) // 2
            
            # 影を描画
            draw.text((text_x + 2, text_y + 2), text, fill='gray', font=font)
            # メインテキストを描画
            draw.text((text_x, text_y), text, fill='black', font=font)
            
            # 枠線を追加
            draw.rectangle([(0, 0), (399, 199)], outline='black', width=2)
            
            # 画像を保存
            generated_image = tool_dir / "generated_image.png"
            img.save(generated_image)
            
            files_to_return.append({
                "path": str(generated_image),
                "type": "image/png",
                "description": "生成された画像"
            })
            
            context["message_callback"](f"画像を生成しました: {generated_image.name}")
        except ImportError:
            context["message_callback"]("PIL (Pillow) がインストールされていないため、画像生成をスキップします")
        except Exception as e:
            context["message_callback"](f"画像生成中にエラーが発生: {str(e)}")
        
        # 例4: JSONファイルを生成
        context["message_callback"]("JSONデータを生成中...")
        json_data = {
            "tool_name": TOOL_NAME,
            "execution_context": {
                "model": context.get("model", "unknown"),
                "thinking_budget": context.get("thinking_budget", 0),
                "mode": mode
            },
            "input": {
                "text": args.get('input_text', ''),
                "timestamp": context.get('timestamp', 'N/A')
            },
            "settings": settings,
            "results": {
                "status": "success",
                "files_generated": len(files_to_return),
                "message": "処理が正常に完了しました"
            }
        }
        
        json_file = tool_dir / "result.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        files_to_return.append({
            "path": str(json_file),
            "type": "application/json",
            "description": "実行結果のJSONデータ"
        })
        context["message_callback"](f"JSONファイルを生成しました: {json_file.name}")
        
        # UIがある場合は起動
        if context.get("ui_port"):
            context["message_callback"]("UIサーバーを起動中...")
            start_ui_server(context["ui_port"], context["tool_dir"])
            context["message_callback"](f"UIサーバーがポート {context['ui_port']} で起動しました")
        
        # 処理完了
        context["message_callback"]("すべての処理が完了しました")
        
        # 成功時の応答（ファイルを含む）
        result_text = f"処理が完了しました。{len(files_to_return)}個のファイルを添付しています。"
        
        return {
            "success": True,
            "result": result_text,
            "files": files_to_return,  # AIに渡すファイルのリスト
            "metadata": {
                "mode": mode,
                "files_count": len(files_to_return),
                "cache_enabled": enable_cache
            }
        }
        
    except Exception as e:
        context["message_callback"](f"エラーが発生しました: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def process_input(text: str, settings: dict) -> str:
    """実際の処理を行う関数（カスタマイズ用）"""
    mode = settings.get("mode", "standard")
    
    if mode == "debug":
        return f"[DEBUG] 入力: {text}"
    elif mode == "advanced":
        return f"[ADVANCED] 処理結果: {text.upper()}"
    else:
        return f"[STANDARD] 処理結果: {text}"

def start_ui_server(port: int, tool_dir: str):
    """UIサーバーを起動"""
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        index_path = Path(tool_dir) / "index.html"
        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # index.htmlが存在しない場合のデフォルトHTML
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Sample Tool UI</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 40px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                    }
                    .container {
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 10px;
                        padding: 30px;
                        backdrop-filter: blur(10px);
                    }
                    h1 {
                        margin-bottom: 20px;
                    }
                    .info {
                        background: rgba(255, 255, 255, 0.2);
                        padding: 15px;
                        border-radius: 5px;
                        margin: 10px 0;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔧 Sample Tool UI</h1>
                    <div class="info">
                        <strong>Status:</strong> Running
                    </div>
                    <div class="info">
                        <strong>Port:</strong> """ + str(port) + """
                    </div>
                    <div class="info">
                        <strong>Tool Directory:</strong> """ + tool_dir + """
                    </div>
                    <p>This is the default UI for the sample tool. Create an index.html file in the tool directory to customize this interface.</p>
                </div>
            </body>
            </html>
            """
    
    @app.route('/status')
    def status():
        """ステータスエンドポイント"""
        return json.dumps({
            "status": "running",
            "port": port,
            "tool_name": TOOL_NAME
        })
    
    # バックグラウンドで起動
    thread = threading.Thread(
        target=lambda: app.run(port=port, debug=False, use_reloader=False),
        daemon=True
    )
    thread.start()
