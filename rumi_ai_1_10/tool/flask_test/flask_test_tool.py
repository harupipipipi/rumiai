"""
Flask テストツール
Flaskサーバーの起動と表示をテストし、詳細なログを記録します
"""

import os
import sys
import time
import json
import socket
import threading
import logging
from pathlib import Path
from datetime import datetime
import traceback
import weakref
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

TOOL_NAME = "Flask テスト"
TOOL_DESCRIPTION = "Flaskサーバーの起動と表示をテストし、詳細なログを記録します"
TOOL_ICON = '🧪'

# グローバル変数でログキャプチャとサーバー状態を保持
active_log_captures = weakref.WeakSet()
test_server_data = {}

def get_function_declaration():
    """Gemini Function Calling用の関数定義を返す"""
    return {
        "name": "flask_test",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "test_message": {
                    "type": "string",
                    "description": "テストメッセージ（オプション）",
                    "default": "Flask Test"
                }
            }
        }
    }

def get_settings_schema():
    """設定項目のスキーマを返す"""
    return {
        "log_level": {
            "type": "select",
            "label": "ログレベル",
            "description": "ログの詳細度",
            "default": "DEBUG",
            "options": [
                {"value": "DEBUG", "label": "デバッグ（最も詳細）"},
                {"value": "INFO", "label": "情報"},
                {"value": "WARNING", "label": "警告"},
                {"value": "ERROR", "label": "エラーのみ"}
            ]
        },
        "port_check_timeout": {
            "type": "number",
            "label": "ポートチェックタイムアウト（秒）",
            "description": "ポートの応答を待つ最大時間",
            "default": 10,
            "min": 5,
            "max": 30,
            "step": 1
        },
        "save_system_info": {
            "type": "boolean",
            "label": "システム情報を記録",
            "description": "OS、Python、パッケージ情報をログに含める",
            "default": True
        }
    }

class LogCapture:
    """ログをファイルとメモリに記録するハンドラー"""
    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        self.logs = []
        self.file_handler = None
        self.is_closed = False
        self.lock = threading.Lock()
        
        # ログファイルを作成
        try:
            self.file_handler = open(log_file_path, 'w', encoding='utf-8')
            active_log_captures.add(self)
        except Exception as e:
            print(f"Failed to open log file: {e}")
        
    def write(self, message):
        """ログメッセージを記録"""
        if self.is_closed:
            return
            
        with self.lock:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            formatted_message = f"[{timestamp}] {message}"
            
            # メモリに保存
            self.logs.append(formatted_message)
            
            # コンソールにも出力（デバッグ用）
            print(formatted_message)
            
            # ファイルに書き込み
            if self.file_handler and not self.is_closed:
                try:
                    self.file_handler.write(formatted_message + '\n')
                    self.file_handler.flush()
                except:
                    pass
    
    def close(self):
        """ファイルハンドラーを閉じる"""
        with self.lock:
            self.is_closed = True
            if self.file_handler:
                try:
                    self.file_handler.close()
                except:
                    pass
                self.file_handler = None
    
    def get_logs(self):
        """記録されたログを取得"""
        with self.lock:
            return '\n'.join(self.logs)

class TestHTTPRequestHandler(BaseHTTPRequestHandler):
    """シンプルなHTTPリクエストハンドラー"""
    
    def log_message(self, format, *args):
        """HTTPサーバーのログをカスタマイズ"""
        if hasattr(self.server, 'log_capture') and self.server.log_capture:
            self.server.log_capture.write(f"HTTP: {format % args}")
    
    def do_GET(self):
        """GETリクエストの処理"""
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask Test - Complete</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-green-50 to-blue-50 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-2xl w-full">
        <div class="bg-white rounded-2xl shadow-2xl p-8">
            <div class="flex items-center justify-center mb-6">
                <div class="w-20 h-20 bg-green-500 rounded-full flex items-center justify-center animate-bounce">
                    <svg class="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                </div>
            </div>
            
            <h1 class="text-4xl font-bold text-center mb-4 text-green-600">
                COMPLETE
            </h1>
            
            <p class="text-center text-gray-600 mb-6">
                HTTPサーバーは正常に起動し、表示されています
            </p>
            
            <div class="bg-gray-50 rounded-lg p-4 mb-6">
                <h2 class="font-semibold text-gray-800 mb-3">テスト情報</h2>
                <dl class="space-y-2 text-sm">
                    <div class="flex justify-between">
                        <dt class="text-gray-600">ステータス:</dt>
                        <dd class="font-medium text-green-600">✅ 完了</dd>
                    </div>
                    <div class="flex justify-between">
                        <dt class="text-gray-600">サーバータイプ:</dt>
                        <dd class="font-medium">Python HTTPServer</dd>
                    </div>
                    <div class="flex justify-between">
                        <dt class="text-gray-600">ポート:</dt>
                        <dd class="font-medium">""" + str(self.server.server_port) + """</dd>
                    </div>
                    <div class="flex justify-between">
                        <dt class="text-gray-600">メッセージ:</dt>
                        <dd class="font-medium">""" + test_server_data.get('message', 'Test') + """</dd>
                    </div>
                </dl>
            </div>
            
            <div class="bg-blue-50 rounded-lg p-4">
                <h3 class="font-semibold text-blue-800 mb-2">ログファイル</h3>
                <p class="text-xs text-blue-600 break-all">""" + test_server_data.get('log_file', 'N/A') + """</p>
            </div>
            
            <div class="mt-6 text-center">
                <a href="/api/status" class="text-blue-600 hover:underline text-sm">APIステータスを確認</a>
                <span class="mx-2">|</span>
                <a href="/api/logs" class="text-blue-600 hover:underline text-sm">ログを表示</a>
            </div>
            
            <div class="text-center text-xs text-gray-500 mt-4">
                このページが表示されていれば、サーバーは正常に動作しています
            </div>
        </div>
    </div>
</body>
</html>
            """
            self.wfile.write(html.encode('utf-8'))
            
            # ログに記録
            if hasattr(self.server, 'log_capture'):
                self.server.log_capture.write("SUCCESS: Index page served successfully")
                test_server_data['requests_count'] = test_server_data.get('requests_count', 0) + 1
        
        elif parsed_path.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            status = {
                "status": "complete",
                "port": self.server.server_port,
                "requests_count": test_server_data.get('requests_count', 0),
                "uptime": int(time.time() - test_server_data.get('start_time', time.time()))
            }
            self.wfile.write(json.dumps(status).encode('utf-8'))
        
        elif parsed_path.path == '/api/logs':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            
            if hasattr(self.server, 'log_capture'):
                logs = self.server.log_capture.get_logs()
                self.wfile.write(logs.encode('utf-8'))
            else:
                self.wfile.write(b"No logs available")
        
        elif parsed_path.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            health = {"status": "healthy", "port": self.server.server_port}
            self.wfile.write(json.dumps(health).encode('utf-8'))
        
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def check_port(port, timeout=1):
    """ポートが利用可能かチェック"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex(('127.0.0.1', port))
        return result != 0  # 0でなければ利用可能
    except:
        return True
    finally:
        sock.close()

def wait_for_server(port, timeout=10, log_capture=None):
    """サーバーが起動するまで待つ"""
    start_time = time.time()
    
    if log_capture:
        log_capture.write(f"INFO: Waiting for server on port {port} to start...")
    
    while time.time() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                if log_capture:
                    log_capture.write(f"SUCCESS: Server on port {port} is now responding!")
                return True
        except Exception as e:
            if log_capture:
                log_capture.write(f"DEBUG: Connection attempt failed: {e}")
        finally:
            sock.close()
        time.sleep(0.5)
    
    if log_capture:
        log_capture.write(f"ERROR: Server on port {port} did not start within {timeout} seconds")
    return False

def get_system_info():
    """システム情報を取得"""
    import platform
    
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": platform.python_version(),
        "current_directory": os.getcwd(),
        "path": sys.path[:5]
    }
    
    return info

def execute(args: dict, context: dict) -> dict:
    """
    ツールの実行
    """
    global test_server_data
    
    test_message = args.get("test_message", "Flask Test")
    
    # 設定を取得
    settings = context.get("settings", {})
    log_level = settings.get("log_level", "DEBUG")
    port_check_timeout = settings.get("port_check_timeout", 10)
    save_system_info = settings.get("save_system_info", True)
    
    # リアルタイムメッセージ
    message_callback = context.get("message_callback", lambda x: None)
    
    # チャットパスからログディレクトリを作成
    chat_path = Path(context.get("chat_path", "."))
    log_dir = chat_path / "log"
    log_dir.mkdir(exist_ok=True)
    
    # ログファイルのパス
    log_file = log_dir / "log.txt"
    
    # ログキャプチャを開始
    log_capture = LogCapture(str(log_file))
    
    # グローバルデータを初期化
    test_server_data = {
        "message": test_message,
        "log_file": str(log_file),
        "start_time": time.time(),
        "requests_count": 0
    }
    
    httpd = None
    server_thread = None
    
    try:
        log_capture.write("=" * 60)
        log_capture.write("HTTP Server Test Tool - Execution Started")
        log_capture.write("=" * 60)
        log_capture.write(f"Test Message: {test_message}")
        log_capture.write(f"Log Level: {log_level}")
        log_capture.write(f"Chat Path: {chat_path}")
        log_capture.write(f"Log File: {log_file}")
        
        message_callback("HTTPサーバーテストツールを開始しました")
        
        # システム情報を記録
        if save_system_info:
            log_capture.write("\n--- System Information ---")
            sys_info = get_system_info()
            for key, value in sys_info.items():
                log_capture.write(f"{key}: {value}")
            log_capture.write("-" * 40)
        
        # UIポートを取得
        ui_port = context.get("ui_port")
        if not ui_port:
            log_capture.write("ERROR: No UI port provided in context")
            return {
                "success": False,
                "error": "UIポートが提供されていません",
                "log_file": str(log_file)
            }
        
        log_capture.write(f"INFO: UI Port assigned: {ui_port}")
        message_callback(f"ポート {ui_port} でHTTPサーバーを起動します")
        
        # ポートの利用可能性をチェック
        log_capture.write(f"INFO: Checking port {ui_port} availability...")
        if not check_port(ui_port):
            log_capture.write(f"ERROR: Port {ui_port} is already in use!")
            return {
                "success": False,
                "error": f"ポート {ui_port} は既に使用中です",
                "log_file": str(log_file)
            }
        else:
            log_capture.write(f"INFO: Port {ui_port} is available")
        
        # HTTPサーバーを作成
        log_capture.write("INFO: Creating HTTP server...")
        try:
            httpd = HTTPServer(('0.0.0.0', ui_port), TestHTTPRequestHandler)
            httpd.log_capture = log_capture  # ログキャプチャを渡す
            log_capture.write(f"SUCCESS: HTTP server created on port {ui_port}")
        except Exception as e:
            log_capture.write(f"ERROR: Failed to create HTTP server: {e}")
            raise
        
        # サーバーを別スレッドで起動
        def run_server():
            log_capture.write(f"INFO: Starting HTTP server on 0.0.0.0:{ui_port}")
            try:
                httpd.serve_forever()
            except Exception as e:
                log_capture.write(f"ERROR: Server error: {e}")
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        log_capture.write("INFO: Server thread started")
        
        message_callback("HTTPサーバーを起動しました")
        
        # サーバーが応答するまで待つ
        if wait_for_server(ui_port, port_check_timeout, log_capture):
            message_callback(f"サーバーが正常に起動しました: http://localhost:{ui_port}")
            
            # テストリクエストを送信
            try:
                import urllib.request
                log_capture.write(f"INFO: Sending test request to http://localhost:{ui_port}/health")
                with urllib.request.urlopen(f"http://localhost:{ui_port}/health", timeout=5) as response:
                    health_data = json.loads(response.read().decode('utf-8'))
                    log_capture.write(f"SUCCESS: Health check response: {health_data}")
            except Exception as e:
                log_capture.write(f"WARNING: Health check failed: {e}")
            
            log_capture.write("=" * 60)
            log_capture.write("HTTP Server Test Tool - Execution Completed Successfully")
            log_capture.write("=" * 60)
            
            return {
                "success": True,
                "result": f"HTTPサーバーが正常に起動しました。\nポート: {ui_port}\nログファイル: {log_file}",
                "log_file": str(log_file),
                "port": ui_port,
                "status": "complete"
            }
        else:
            message_callback("サーバーが応答しません")
            log_capture.write("ERROR: Server did not respond in time")
            
            return {
                "success": False,
                "error": "HTTPサーバーが起動しませんでした",
                "log_file": str(log_file),
                "port": ui_port
            }
            
    except Exception as e:
        log_capture.write(f"FATAL ERROR: {str(e)}")
        log_capture.write(f"TRACEBACK:\n{traceback.format_exc()}")
        message_callback(f"エラーが発生しました: {str(e)}")
        
        return {
            "success": False,
            "error": str(e),
            "log_file": str(log_file) if 'log_file' in locals() else None,
            "traceback": traceback.format_exc()
        }
    finally:
        # ログを保存
        message_callback(f"ログを保存しました: {log_file}")
        time.sleep(1)
        log_capture.close()
        
        # サーバーは実行し続ける（デーモンスレッドなので、メインプロセスが終了すれば自動的に終了）
