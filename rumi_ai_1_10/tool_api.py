# tool_api.py
import json
import time
from flask import jsonify, Response, request
from typing import Generator, Dict, Any

class ToolAPI:
    """ツール関連のAPIエンドポイント処理"""
    
    def __init__(self, gemini_client):
        self.gemini_client = gemini_client
        self.tool_loader = gemini_client.tool_loader if gemini_client else None
    
    def get_tool_messages(self) -> Dict[str, Any]:
        """ツールからのリアルタイムメッセージを取得"""
        if not self.tool_loader:
            return {'messages': []}
        
        messages = self.tool_loader.get_tool_messages()
        return {'messages': messages}
    
    def stream_tool_messages(self) -> Response:
        """ツールメッセージをSSE（Server-Sent Events）でストリーミング"""
        def generate() -> Generator[str, None, None]:
            while True:
                if self.tool_loader:
                    messages = self.tool_loader.get_tool_messages()
                    for msg in messages:
                        yield f"data: {json.dumps(msg)}\n\n"
                time.sleep(0.1)  # 100msごとにチェック
        
        return Response(generate(), mimetype='text/event-stream')
    
    def get_tool_ui_info(self, tool_name: str) -> tuple:
        """特定のツールのUI情報を取得"""
        if not self.tool_loader:
            return jsonify({'error': 'Tool loader not initialized'}), 500
        
        tool_info = self.tool_loader.loaded_tools.get(tool_name)
        if not tool_info:
            return jsonify({'error': 'Tool not found'}), 404
        
        return jsonify({
            'has_ui': tool_info.get('has_ui', False),
            'port': tool_info.get('port'),
            'icon': tool_info.get('icon', ''),
            'name': tool_info.get('name', '')
        }), 200
    
    def reload_tools(self) -> tuple:
        """ツールを再読み込みする"""
        if not self.tool_loader:
            return jsonify({
                'success': False,
                'error': 'Tool loader not initialized'
            }), 500
        
        try:
            result = self.tool_loader.reload_all_tools()
            return jsonify(result), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    def get_all_tools_settings(self) -> tuple:
        """すべてのツールと設定を取得"""
        if not self.tool_loader:
            return jsonify({}), 200
        
        tools_data = self.tool_loader.get_all_tools_with_settings()
        return jsonify(tools_data), 200
    
    def update_tool_settings(self, tool_name: str) -> tuple:
        """特定のツールの設定を更新"""
        if not self.tool_loader:
            return jsonify({'success': False, 'error': 'Tool loader not initialized'}), 500
        
        settings = request.json
        success = self.tool_loader.update_tool_settings(tool_name, settings)
        
        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to update settings'}), 500
    
    def delete_tool_settings(self, tool_name: str) -> tuple:
        """特定のツールの設定を削除（設定のリセット）"""
        if not self.tool_loader:
            return jsonify({'success': False, 'error': 'Tool loader not initialized'}), 500
        
        if tool_name in self.tool_loader.tool_settings:
            del self.tool_loader.tool_settings[tool_name]
            self.tool_loader._save_settings()
            return jsonify({'success': True}), 200
        
        return jsonify({'success': False, 'error': 'Tool settings not found'}), 404
    
    def get_tool_venv_status(self, tool_name: str) -> tuple:
        """特定のツールの仮想環境ステータスを取得"""
        if not self.tool_loader:
            return jsonify({'error': 'Tool loader not initialized'}), 500
        
        tool_info = self.tool_loader.loaded_tools.get(tool_name)
        if not tool_info:
            return jsonify({'error': 'Tool not found'}), 404
        
        from pathlib import Path
        import subprocess
        
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
                    status['packages'] = json.loads(result.stdout)
            except:
                pass
        
        return jsonify(status), 200
    
    def debug_tools(self) -> tuple:
        """ツールのデバッグ情報を取得"""
        if not self.tool_loader:
            return jsonify({
                'total_tools': 0,
                'tools': {},
                'duplicates': {},
                'has_duplicates': False
            }), 200
        
        tools_info = {}
        
        for tool_name, tool_data in self.tool_loader.loaded_tools.items():
            tools_info[tool_name] = {
                'display_name': tool_data['name'],
                'function_name': tool_data['function_declaration']['name'],
                'file_path': tool_data['file_path'],
                'tool_dir': tool_data['tool_dir']
            }
        
        # 重複チェック
        function_names = {}
        for tool_name, info in tools_info.items():
            func_name = info['function_name']
            if func_name not in function_names:
                function_names[func_name] = []
            function_names[func_name].append(info)
        
        duplicates = {k: v for k, v in function_names.items() if len(v) > 1}
        
        return jsonify({
            'total_tools': len(tools_info),
            'tools': tools_info,
            'duplicates': duplicates,
            'has_duplicates': len(duplicates) > 0
        }), 200
