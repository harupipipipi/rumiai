# ecosystem/default/backend/components/supporter/supporter_loader.py
"""
サポーターの動的読み込みと管理を行うモジュール
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional


class AIHelper:
    """
    サポーター用AIヘルパー
    サポーターがAI機能を利用するためのインターフェース
    """
    
    def __init__(
        self,
        ai_manager,
        ai_config: Dict[str, Any],
        current_model_id: str,
        supporter_settings: Dict[str, Any]
    ):
        """
        AIHelperを初期化
        
        Args:
            ai_manager: AIClientインスタンス
            ai_config: manifest.jsonのai_config
            current_model_id: 現在のチャットで使用中のモデルID
            supporter_settings: サポーター固有の設定（history.jsonから）
        """
        self.ai_manager = ai_manager
        self.ai_config = ai_config or {}
        self.current_model_id = current_model_id
        self.supporter_settings = supporter_settings or {}
        
        # モデルIDを解決
        self._resolved_model_id = self._resolve_model_id()
    
    def _resolve_model_id(self) -> str:
        """ai_configに基づいてモデルIDを解決"""
        mode = self.ai_config.get('mode', 'current')
        
        if mode == 'fixed':
            return self.ai_config.get('model_id', self.current_model_id)
        elif mode == 'current':
            return self.current_model_id
        elif mode == 'user':
            # ユーザーがUIで選択したモデルID
            return self.supporter_settings.get('selected_model_id', self.current_model_id)
        else:
            return self.current_model_id
    
    def get_response(self, system_prompt: str, user_message: str) -> str:
        """
        設定に基づいたAIモデルから応答を取得
        
        Args:
            system_prompt: システムプロンプト
            user_message: ユーザーメッセージ
        
        Returns:
            AIの応答テキスト
        """
        return self.get_response_with_model(
            model_id=self._resolved_model_id,
            system_prompt=system_prompt,
            user_message=user_message
        )
    
    def get_response_with_model(
        self,
        model_id: str,
        system_prompt: str,
        user_message: str
    ) -> str:
        """
        指定したモデルIDで応答を取得
        
        Args:
            model_id: 使用するモデルID
            system_prompt: システムプロンプト
            user_message: ユーザーメッセージ
        
        Returns:
            AIの応答テキスト
        """
        if not self.ai_manager:
            raise RuntimeError("AI manager is not initialized")
        
        try:
            # 空の履歴を作成
            empty_history = {
                "conversation_id": "supporter_temp",
                "messages": [],
                "mapping": {},
                "current_node": None,
                "schema_version": "2.0"
            }
            
            # 非ストリーミングでリクエスト
            response = self.ai_manager.send_request(
                model_id=model_id,
                history=empty_history,
                current_text_input=user_message,
                current_file_paths=[],
                system_prompt=system_prompt,
                temperature=0.7,
                thinking_budget=None,
                tools=None,
                use_loaded_tools=False
            )
            
            # テキストを抽出
            if self.ai_manager.current_client:
                return self.ai_manager.current_client.extract_response_text(response)
            
            # フォールバック
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'candidates') and response.candidates:
                text = ""
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text'):
                        text += part.text
                return text
            
            return str(response)
            
        except Exception as e:
            raise RuntimeError(f"AI request failed: {e}")
    
    def list_available_models(self) -> List[Dict[str, Any]]:
        """
        利用可能なモデル一覧を取得
        
        Returns:
            モデル情報のリスト
        """
        if not self.ai_manager:
            return []
        
        return self.ai_manager.get_available_models()


class SupporterLoader:
    """
    サポーターの動的読み込みと管理を行うクラス
    """
    
    def __init__(self, supporter_dir: str = None):
        """
        SupporterLoaderを初期化
        
        Args:
            supporter_dir: サポーターディレクトリのパス
        """
        if supporter_dir is None:
            # エコシステム経由でパス解決を試みる
            try:
                from backend_core.ecosystem.compat import get_supporters_assets_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    supporter_dir = get_supporters_assets_dir()
                else:
                    supporter_dir = 'supporter'
            except ImportError:
                supporter_dir = 'supporter'
        
        self.supporter_dir = Path(supporter_dir)
        self.loaded_supporters: Dict[str, Dict[str, Any]] = {}
        self.supporter_settings: Dict[str, Dict[str, Any]] = {}
        self._settings_file = self.supporter_dir / 'supporter_settings.json'
        
        # ディレクトリが存在しない場合は作成
        if not self.supporter_dir.exists():
            self.supporter_dir.mkdir(parents=True)
        
        # 設定を読み込み
        self._load_settings()
    
    def _load_settings(self):
        """サポーター設定を読み込み"""
        if self._settings_file.exists():
            try:
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    self.supporter_settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.supporter_settings = {}
    
    def _save_settings(self):
        """サポーター設定を保存"""
        try:
            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.supporter_settings, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"サポーター設定の保存に失敗: {e}")
    
    def load_all_supporters(self) -> Dict[str, Dict[str, Any]]:
        """
        すべてのサポーターを読み込み
        
        Returns:
            読み込まれたサポーター情報の辞書
        """
        self.loaded_supporters = {}
        
        if not self.supporter_dir.exists():
            return self.loaded_supporters
        
        for item in self.supporter_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                manifest_file = item / 'manifest.json'
                if manifest_file.exists():
                    try:
                        supporter_info = self._load_supporter(item)
                        if supporter_info:
                            supporter_name = item.name
                            self.loaded_supporters[supporter_name] = supporter_info
                            print(f"サポーター読み込み成功: {supporter_name}")
                    except Exception as e:
                        print(f"サポーター読み込みエラー ({item.name}): {e}")
        
        print(f"読み込まれたサポーター数: {len(self.loaded_supporters)}")
        return self.loaded_supporters
    
    def _load_supporter(self, supporter_path: Path) -> Optional[Dict[str, Any]]:
        """
        単一のサポーターを読み込み
        
        Args:
            supporter_path: サポーターディレクトリのパス
        
        Returns:
            サポーター情報またはNone
        """
        manifest_file = supporter_path / 'manifest.json'
        
        # manifest.json を読み込み
        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        supporter_name = supporter_path.name
        
        # サポーターモジュールを読み込み
        module_file = supporter_path / f'{supporter_name}_supporter.py'
        if not module_file.exists():
            print(f"サポーターモジュールが見つかりません: {module_file}")
            return None
        
        # モジュールを動的にインポート
        spec = importlib.util.spec_from_file_location(
            f"supporter_{supporter_name}",
            module_file
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"supporter_{supporter_name}"] = module
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"サポーターモジュール実行エラー ({supporter_name}): {e}")
            return None
        
        # execute関数の存在確認
        if not hasattr(module, 'execute'):
            print(f"サポーターにexecute関数がありません: {supporter_name}")
            return None
        
        return {
            'name': manifest.get('name', supporter_name),
            'description': manifest.get('description', ''),
            'version': manifest.get('version', '1.0.0'),
            'timing': manifest.get('timing', 'pre'),
            'output_scope': manifest.get('output_scope', 'temporary'),
            'enabled': manifest.get('enabled', True),
            'icon': manifest.get('icon', '🔧'),
            'ai_config': manifest.get('ai_config'),
            'settings_schema': manifest.get('settings_schema'),
            'module': module,
            'manifest': manifest,
            'supporter_dir': str(supporter_path)
        }
    
    def reload_all_supporters(self) -> Dict[str, Any]:
        """すべてのサポーターを再読み込み"""
        # キャッシュをクリア
        for name in list(self.loaded_supporters.keys()):
            module_name = f"supporter_{name}"
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        self.loaded_supporters = {}
        self.load_all_supporters()
        
        return {
            'success': True,
            'loaded_count': len(self.loaded_supporters),
            'supporters': list(self.loaded_supporters.keys())
        }
    
    def get_supporter(self, supporter_name: str) -> Optional[Dict[str, Any]]:
        """指定されたサポーターを取得"""
        return self.loaded_supporters.get(supporter_name)
    
    def get_all_supporters_info(self) -> List[Dict[str, Any]]:
        """
        すべてのサポーター情報を取得（UIに表示用）
        
        Returns:
            サポーター情報のリスト
        """
        result = []
        for name, info in self.loaded_supporters.items():
            result.append({
                'id': name,
                'name': info['name'],
                'description': info['description'],
                'version': info['version'],
                'timing': info['timing'],
                'output_scope': info['output_scope'],
                'enabled': info['enabled'],
                'icon': info['icon'],
                'has_ai': info.get('ai_config') is not None,
                'ai_mode': info.get('ai_config', {}).get('mode') if info.get('ai_config') else None,
                'settings_schema': info.get('settings_schema')
            })
        return result
    
    def execute_supporter(
        self,
        supporter_name: str,
        context: Dict[str, Any],
        ai_manager=None
    ) -> Dict[str, Any]:
        """
        サポーターを実行
        
        Args:
            supporter_name: サポーター名
            context: 実行コンテキスト
            ai_manager: AIClientインスタンス（AI機能使用時）
        
        Returns:
            実行結果
        """
        supporter_info = self.loaded_supporters.get(supporter_name)
        if not supporter_info:
            return {'error': f'Supporter not found: {supporter_name}'}
        
        module = supporter_info.get('module')
        if not module or not hasattr(module, 'execute'):
            return {'error': f'Supporter has no execute function: {supporter_name}'}
        
        # ai_helper を作成してコンテキストに注入
        if supporter_info.get('ai_config') and ai_manager:
            ai_helper = AIHelper(
                ai_manager=ai_manager,
                ai_config=supporter_info['ai_config'],
                current_model_id=context.get('current_model_id', 'gemini-2.5-flash'),
                supporter_settings=context.get('supporter_settings', {}).get(supporter_name, {})
            )
            context['ai_helper'] = ai_helper
        
        # サポーター固有の設定を注入
        context['settings'] = self.supporter_settings.get(supporter_name, {})
        
        try:
            result = module.execute(context)
            return result if result else {}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    def update_supporter_settings(
        self,
        supporter_name: str,
        settings: Dict[str, Any]
    ) -> bool:
        """サポーターの設定を更新"""
        self.supporter_settings[supporter_name] = settings
        self._save_settings()
        return True
    
    def get_supporter_settings(self, supporter_name: str) -> Dict[str, Any]:
        """サポーターの設定を取得"""
        return self.supporter_settings.get(supporter_name, {})
    
    def is_supporter_available(self, supporter_name: str) -> bool:
        """サポーターが利用可能かチェック"""
        return supporter_name in self.loaded_supporters
    
    def get_supporters_by_timing(self, timing: str) -> List[str]:
        """
        指定されたタイミングのサポーター名リストを取得
        
        Args:
            timing: 'pre', 'post', or 'both'
        
        Returns:
            サポーター名のリスト
        """
        result = []
        for name, info in self.loaded_supporters.items():
            supporter_timing = info.get('timing', 'pre')
            if supporter_timing == timing or supporter_timing == 'both':
                result.append(name)
        return result
