# tool_ui_manager.py
"""
ツールUIサーバーの管理を行うモジュール
各ツールのUIサーバーの起動・停止・ポート管理を担当
"""

import threading
import time
from typing import Dict, Optional, Any
from pathlib import Path

class ToolUIManager:
    """ツールUIサーバーを管理するクラス"""
    
    def __init__(self):
        self.active_servers: Dict[str, Dict[str, Any]] = {}
        self.server_lock = threading.Lock()
    
    def start_tool_ui(self, tool_name: str, tool_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        ツールのUIサーバーを起動
        
        Args:
            tool_name: ツール名（function name）
            tool_info: ツール情報（loaded_toolsから取得）
            
        Returns:
            UI情報（ポート番号、URL等）またはNone
        """
        with self.server_lock:
            # 既に起動している場合はその情報を返す
            if tool_name in self.active_servers:
                server_info = self.active_servers[tool_name]
                if server_info.get('active'):
                    print(f"UIサーバーは既に起動中: {tool_name} (port: {server_info['port']})")
                    return {
                        'ui_available': True,
                        'ui_port': server_info['port'],
                        'html_file': server_info.get('html_file', 'index.html'),
                        'ui_url': f"http://localhost:{server_info['port']}/{server_info.get('html_file', 'index.html')}"
                    }
        
        # UIがないツールの場合
        if not tool_info.get('has_ui'):
            return None
        
        # モジュールからstart_ui_server関数を取得
        module = tool_info.get('module')
        if not module or not hasattr(module, 'start_ui_server'):
            print(f"ツール {tool_name} にstart_ui_server関数がありません")
            return None
        
        try:
            # UIサーバーを起動
            print(f"UIサーバーを起動中: {tool_name}")
            ui_port = module.start_ui_server()
            
            if ui_port:
                # サーバー情報を保存
                server_info = {
                    'port': ui_port,
                    'tool_name': tool_info.get('name', tool_name),
                    'html_file': tool_info.get('html_file', 'index.html'),
                    'started_at': time.time(),
                    'active': True,
                    'module': module
                }
                
                with self.server_lock:
                    self.active_servers[tool_name] = server_info
                
                print(f"UIサーバー起動成功: {tool_name} on port {ui_port}")
                
                return {
                    'ui_available': True,
                    'ui_port': ui_port,
                    'html_file': server_info['html_file'],
                    'ui_url': f"http://localhost:{ui_port}/{server_info['html_file']}"
                }
            else:
                print(f"UIサーバーの起動に失敗: {tool_name}")
                return None
                
        except Exception as e:
            print(f"UIサーバー起動エラー ({tool_name}): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def stop_tool_ui(self, tool_name: str) -> bool:
        """
        ツールのUIサーバーを停止
        
        Args:
            tool_name: ツール名（function name）
            
        Returns:
            停止成功の可否
        """
        with self.server_lock:
            if tool_name not in self.active_servers:
                return False
            
            server_info = self.active_servers[tool_name]
            module = server_info.get('module')
            
            # stop_ui_server関数があれば呼び出し
            if module and hasattr(module, 'stop_ui_server'):
                try:
                    module.stop_ui_server()
                    print(f"UIサーバーを停止: {tool_name}")
                except Exception as e:
                    print(f"UIサーバー停止エラー ({tool_name}): {e}")
            
            # サーバー情報を削除
            del self.active_servers[tool_name]
            return True
    
    def stop_all_ui_servers(self):
        """すべてのUIサーバーを停止"""
        with self.server_lock:
            tool_names = list(self.active_servers.keys())
        
        for tool_name in tool_names:
            self.stop_tool_ui(tool_name)
        
        print("すべてのUIサーバーを停止しました")
    
    def get_active_servers(self) -> Dict[str, Dict[str, Any]]:
        """アクティブなサーバーの情報を取得"""
        with self.server_lock:
            return {
                name: {
                    'port': info['port'],
                    'tool_name': info['tool_name'],
                    'html_file': info['html_file'],
                    'uptime': time.time() - info['started_at']
                }
                for name, info in self.active_servers.items()
                if info.get('active')
            }
    
    def is_server_active(self, tool_name: str) -> bool:
        """サーバーがアクティブかチェック"""
        with self.server_lock:
            return tool_name in self.active_servers and self.active_servers[tool_name].get('active', False)
    
    def get_server_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """特定のサーバー情報を取得"""
        with self.server_lock:
            if tool_name in self.active_servers:
                info = self.active_servers[tool_name]
                return {
                    'ui_available': True,
                    'ui_port': info['port'],
                    'html_file': info['html_file'],
                    'ui_url': f"http://localhost:{info['port']}/{info['html_file']}",
                    'uptime': time.time() - info['started_at']
                }
        return None
    
    def cleanup_inactive_servers(self, timeout: int = 3600):
        """
        非アクティブなサーバーをクリーンアップ
        
        Args:
            timeout: タイムアウト時間（秒）
        """
        current_time = time.time()
        servers_to_stop = []
        
        with self.server_lock:
            for tool_name, info in self.active_servers.items():
                if current_time - info['started_at'] > timeout:
                    servers_to_stop.append(tool_name)
        
        for tool_name in servers_to_stop:
            print(f"タイムアウトによりUIサーバーを停止: {tool_name}")
            self.stop_tool_ui(tool_name)

# グローバルインスタンス
tool_ui_manager = ToolUIManager()
