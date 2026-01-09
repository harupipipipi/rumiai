# ai_manager.py 完全版

"""
AIクライアントの統合管理システム
複数のAIプロバイダーを統一的に扱うためのインターフェース
"""

import os
import json
import uuid
import sys
import datetime
import traceback
from typing import List, Optional, Dict, Any, Iterator
from pathlib import Path
import threading

# パスを追加（tool/ を参照可能にする）
tool_path = Path(__file__).parent / "tool"
if str(tool_path) not in sys.path:
    sys.path.insert(0, str(tool_path))

# ai_client_loaderをインポート
from ai_client.ai_client_loader import AIClientLoader

# ToolLoaderのインポート（複数のフォールバック対応）
try:
    from tool_loader import ToolLoader
except ImportError:
    try:
        from tool.tool_loader import ToolLoader
    except ImportError:
        # 最終フォールバック: ファイルパスから動的読み込み
        import importlib.util as _imp_util
        _tool_loader_path = Path(__file__).parent / "tool" / "tool_loader.py"
        if _tool_loader_path.exists():
            _spec = _imp_util.spec_from_file_location("tool_loader", _tool_loader_path)
            _module = _imp_util.module_from_spec(_spec)
            sys.modules["tool_loader"] = _module
            _spec.loader.exec_module(_module)
            ToolLoader = _module.ToolLoader
        else:
            raise ImportError(f"ToolLoader が見つかりません: {_tool_loader_path}")

# tool_ui_managerのインポート
from tool_ui_manager import tool_ui_manager

# chat_managerから標準形式ヘルパーをインポート
from chat_manager import create_standard_history

# 設定マネージャーのキャッシュ（モジュールレベル）
_settings_manager_instance = None

def _get_settings_manager():
    """SettingsManagerをシングルトンで取得（遅延インポート）"""
    global _settings_manager_instance
    
    if _settings_manager_instance is not None:
        return _settings_manager_instance
    
    try:
        from settings_manager import SettingsManager
        _settings_manager_instance = SettingsManager()
        return _settings_manager_instance
    except ImportError:
        return None


class AIClient:
    """
    統合AIクライアント
    複数のAIプロバイダーを統一的に扱う
    """

    def __init__(self):
        """AIクライアントを初期化"""
        print("統合AIクライアントを初期化中...")
        
        # AIクライアントローダーの初期化
        self.ai_loader = AIClientLoader()
        self.ai_loader.load_all_clients()
        
        # 現在のクライアントインスタンス
        self.current_client = None
        self.current_provider = None
        self.current_model_id = None
        
        # ツールローダーの初期化（プロバイダー非依存）
        self.tool_loader = ToolLoader()
        self.tool_loader.load_all_tools()
        print(f"読み込まれたツール数: {len(self.tool_loader.loaded_tools)}")
        
        # 強制停止用のプロパティ
        self.current_stream = None
        self.stop_event = threading.Event()
        self.aborted_text = ""
        
        # デバッグログ設定
        self.debug_logging = False
        self.debug_log_file = Path("debug.txt")
        
        # デフォルトプロバイダーとモデルの設定
        self._initialize_default_client()
    
    def _write_debug_log(self, message: str, data: Any = None):
        """デバッグログをファイルに書き込み"""
        if not self.debug_logging:
            return
            
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_entry = f"\n{'='*80}\n[{timestamp}] {message}\n"
            
            # APIキー情報を追加
            if self.current_client and hasattr(self.current_client, 'get_masked_api_key'):
                masked_key = self.current_client.get_masked_api_key()
                log_entry += f"API Key: {masked_key}\n"
            
            if data is not None:
                if isinstance(data, (dict, list)):
                    log_entry += json.dumps(data, ensure_ascii=False, indent=2)
                else:
                    log_entry += str(data)
            
            log_entry += "\n"
            
            with open(self.debug_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"デバッグログ書き込みエラー: {e}")
    
    def set_debug_logging(self, enabled: bool):
        """デバッグログの有効/無効を設定"""
        self.debug_logging = enabled
        if enabled:
            self._write_debug_log("=== デバッグログ開始 ===")
        else:
            self._write_debug_log("=== デバッグログ終了 ===")
    
    def _initialize_default_client(self):
        """
        デフォルトのAIクライアントを初期化
        
        優先順位:
        1. ユーザー設定で指定されたモデル
        2. 利用可能なモデルから自動選択
        """
        default_model_id = None
        
        # 1. ユーザー設定からモデルを取得
        try:
            settings_manager = _get_settings_manager()
            if settings_manager:
                user_settings = settings_manager.get_user_settings()
                saved_model = user_settings.get('model')
                if saved_model and saved_model in self.ai_loader.model_profiles:
                    default_model_id = saved_model
                    print(f"ユーザー設定からモデルを読み込み: {default_model_id}")
        except Exception as e:
            print(f"ユーザー設定の読み込みに失敗: {e}")
        
        # 2. 利用可能なモデルから自動選択
        if not default_model_id:
            available_models = self.ai_loader.get_all_models()
            
            if available_models:
                # 優先度順にモデルを選択
                # Function Calling対応 > ストリーミング対応 > その他
                priority_models = []
                fallback_models = []
                
                for model in available_models:
                    features = model.get('features', {})
                    if features.get('supports_function_calling') or features.get('supports_tool_use'):
                        priority_models.append(model)
                    else:
                        fallback_models.append(model)
                
                if priority_models:
                    default_model_id = priority_models[0]['id']
                elif fallback_models:
                    default_model_id = fallback_models[0]['id']
        
        # デフォルトモデルを設定
        if default_model_id:
            if self.set_model(default_model_id):
                print(f"デフォルトモデル: {default_model_id}")
            else:
                print(f"警告: デフォルトモデル {default_model_id} の設定に失敗しました")
        else:
            print("警告: 利用可能なモデルがありません。APIキーを確認してください。")
    
    def set_model(self, model_id: str, api_key: str = None) -> bool:
        """
        使用するモデルを設定
        
        Args:
            model_id: モデルID
            api_key: APIキー（互換性のため残すが使用しない）
        
        Returns:
            設定成功の可否
        """
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile:
            print(f"エラー: モデル {model_id} が見つかりません")
            return False
        
        provider_name = profile['provider_name']
        
        # クライアントインスタンスを取得（APIキーは各クライアントが自分で取得）
        client = self.ai_loader.get_client(provider_name)
        if not client:
            print(f"エラー: クライアントを初期化できません: {provider_name}")
            return False
        
        self.current_client = client
        self.current_provider = provider_name
        self.current_model_id = model_id
        
        print(f"モデル設定完了: {profile['basic_info']['name']} ({provider_name})")
        return True
    
    def send_request(
        self,
        model_id: str,
        history: Dict,
        current_text_input: str,
        current_file_paths: List[str],
        temperature: float = 0.8,
        thinking_budget: Optional[int] = None,
        tools: Optional[List] = None,
        use_loaded_tools: bool = True,
        system_prompt: str = None,
        **kwargs
    ) -> Any:
        """
        AIモデルにリクエストを送信（非ストリーミング）
        
        Args:
            model_id: モデルID
            history: 標準形式の履歴
            current_text_input: 現在の入力テキスト
            current_file_paths: ファイルパスのリスト
            temperature: 温度パラメータ
            thinking_budget: 思考予算
            tools: ツール定義
            use_loaded_tools: 読み込み済みツールを使用するか
            system_prompt: システムプロンプト
        
        Returns:
            AI応答
        """
        # モデルが現在のものと異なる場合は切り替え
        if model_id != self.current_model_id:
            if not self.set_model(model_id):
                raise ValueError(f"モデル {model_id} の設定に失敗しました")
        
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")
        
        # ツールの準備
        final_tools = None
        if use_loaded_tools and self.tool_loader.loaded_tools:
            # プロバイダー固有の形式に変換
            loaded_tools = self.tool_loader.get_tools_for_provider(self.current_provider)
            if tools:
                final_tools = self._merge_tools(tools, loaded_tools)
            else:
                final_tools = loaded_tools
        elif tools:
            final_tools = tools
        
        # デバッグログ: リクエスト
        self._write_debug_log(f"REQUEST to {self.current_provider} ({model_id})", {
            "model_id": model_id,
            "provider": self.current_provider,
            "temperature": temperature,
            "thinking_budget": thinking_budget,
            "text_input": current_text_input[:500] if current_text_input else None,
            "file_count": len(current_file_paths),
            "tools_count": len(final_tools) if final_tools else 0,
            "has_system_prompt": bool(system_prompt)
        })
        
        try:
            # プロバイダー固有のクライアントに委譲
            response = self.current_client.send_request(
                model_id=model_id,
                history=history,
                current_text_input=current_text_input,
                current_file_paths=current_file_paths,
                temperature=temperature,
                thinking_budget=thinking_budget,
                tools=final_tools,
                system_prompt=system_prompt,
                **kwargs
            )
            
            # デバッグログ: レスポンス
            self._write_debug_log(f"RESPONSE from {self.current_provider} ({model_id})", {
                "success": True,
                "response_type": type(response).__name__,
                "response_text": self.current_client.extract_response_text(response)[:500] if hasattr(self.current_client, 'extract_response_text') else None
            })
            
            return response
            
        except Exception as e:
            # デバッグログ: エラー
            self._write_debug_log(f"ERROR from {self.current_provider} ({model_id})", {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc() if self.debug_logging else None
            })
            raise
    
    def send_request_stream(
        self,
        model_id: str,
        history: Dict,
        current_text_input: str,
        current_file_paths: List[str],
        temperature: float = 0.8,
        thinking_budget: Optional[int] = None,
        tools: Optional[List] = None,
        use_loaded_tools: bool = True,
        abort_signal: Optional[threading.Event] = None,
        system_prompt: str = None,
        **kwargs
    ) -> Iterator:
        """
        ストリーミング版のリクエスト送信
        
        Args:
            model_id: モデルID
            history: 標準形式の履歴
            current_text_input: 現在の入力テキスト
            current_file_paths: ファイルパスのリスト
            temperature: 温度パラメータ
            thinking_budget: 思考予算
            tools: ツール定義
            use_loaded_tools: 読み込み済みツールを使用するか
            abort_signal: 中断シグナル
            system_prompt: システムプロンプト
        
        Returns:
            ストリームイテレータ
        """
        # モデルが現在のものと異なる場合は切り替え
        if model_id != self.current_model_id:
            if not self.set_model(model_id):
                raise ValueError(f"モデル {model_id} の設定に失敗しました")
        
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")
        
        # ストリーミング対応チェック
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile.get('features', {}).get('supports_streaming', False):
            raise ValueError(f"モデル {model_id} はストリーミングに対応していません")
        
        # 停止イベントをリセット
        self.stop_event.clear()
        self.aborted_text = ""
        
        if abort_signal:
            self.stop_event = abort_signal
        
        # ツールの準備
        final_tools = None
        if use_loaded_tools and self.tool_loader.loaded_tools:
            loaded_tools = self.tool_loader.get_tools_for_provider(self.current_provider)
            if tools:
                final_tools = self._merge_tools(tools, loaded_tools)
            else:
                final_tools = loaded_tools
        elif tools:
            final_tools = tools
        
        # デバッグログ: ストリーミングリクエスト
        self._write_debug_log(f"STREAM REQUEST to {self.current_provider} ({model_id})", {
            "model_id": model_id,
            "provider": self.current_provider,
            "temperature": temperature,
            "thinking_budget": thinking_budget,
            "text_input": current_text_input[:500] if current_text_input else None,
            "file_count": len(current_file_paths),
            "tools_count": len(final_tools) if final_tools else 0,
            "has_system_prompt": bool(system_prompt)
        })
        
        # プロバイダー固有のクライアントに委譲
        return self.current_client.send_request_stream(
            model_id=model_id,
            history=history,
            current_text_input=current_text_input,
            current_file_paths=current_file_paths,
            temperature=temperature,
            thinking_budget=thinking_budget,
            tools=final_tools,
            abort_signal=self.stop_event,
            system_prompt=system_prompt,
            **kwargs
        )
    
    def handle_function_calls(
        self,
        response: Any,
        model_id: str,
        history: Dict,
        context: dict = None
    ) -> tuple:
        """
        Function Callを処理
        
        Args:
            response: AI応答
            model_id: モデルID
            history: 標準形式の履歴
            context: 実行コンテキスト
        
        Returns:
            (最終応答, 実行結果リスト)
        """
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")
        
        # コンテキストにtool_loaderを追加
        if context is None:
            context = {}
        context['tool_loader'] = self.tool_loader
        
        # Function Calling対応チェック
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile.get('features', {}).get('supports_function_calling', False):
            return response, []
        
        return self.current_client.handle_function_calls(
            response=response,
            model_id=model_id,
            history=history,
            context=context
        )
    
    def handle_function_calls_stream(
        self,
        stream_response,
        model_id: str,
        history: Dict,
        context: dict = None
    ) -> Iterator:
        """
        ストリーミング版のFunction Call処理
        
        Args:
            stream_response: ストリームイテレータ
            model_id: モデルID
            history: 標準形式の履歴
            context: 実行コンテキスト
        
        Returns:
            処理済みイベントのイテレータ
        """
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")
        
        # コンテキストにtool_loaderを追加
        if context is None:
            context = {}
        context['tool_loader'] = self.tool_loader
        
        return self.current_client.handle_function_calls_stream(
            stream_response=stream_response,
            model_id=model_id,
            history=history,
            context=context
        )
    
    def abort_streaming(self):
        """現在のストリーミングを強制停止"""
        print("abort_streaming called")
        self.stop_event.set()
        
        # プロバイダー固有の停止処理
        if self.current_client and hasattr(self.current_client, 'abort_streaming'):
            self.current_client.abort_streaming()
    
    def get_available_models(self) -> List[Dict]:
        """利用可能なすべてのモデルを取得"""
        return self.ai_loader.get_all_models()
    
    def search_models(self, **kwargs) -> List[Dict]:
        """条件に基づいてモデルを検索"""
        return self.ai_loader.search_models(**kwargs)
    
    def _merge_tools(self, tools1: List, tools2: List) -> List:
        """2つのツールリストをマージ"""
        # プロバイダー固有のマージ処理に委譲
        if self.current_client and hasattr(self.current_client, '_merge_tools'):
            return self.current_client._merge_tools(tools1, tools2)
        
        # デフォルト実装
        return tools1 + tools2
    
    def get_invoke_schema(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        モデルのinvoke_schemaを取得
        
        フロントエンドが「このモデルで入力できる項目」を知るためのスキーマを返す。
        
        Args:
            model_id: モデルID
        
        Returns:
            スキーマ情報（パラメータ、ツール、tier等）
        """
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile:
            return None
        
        # 基本情報
        schema = {
            'model_id': model_id,
            'provider': profile['provider_name'],
            'name': profile['basic_info']['name'],
            'product': profile['basic_info'].get('product'),
            'description': profile['basic_info'].get('description', ''),
            'status': profile['basic_info'].get('status', 'active'),
        }
        
        # パラメータスキーマ
        schema['parameters'] = self._build_parameter_schema(profile)
        
        # 機能情報
        schema['features'] = {
            'supports_function_calling': profile.get('features', {}).get('supports_function_calling', False),
            'supports_tool_use': profile.get('features', {}).get('supports_tool_use', False),
            'supports_streaming': profile.get('features', {}).get('supports_streaming', False),
            'supports_reasoning': profile.get('features', {}).get('supports_reasoning', False),
            'is_multimodal': profile.get('features', {}).get('is_multimodal', False),
            'input_modalities': profile.get('features', {}).get('input_modalities', ['text']),
            'output_modalities': profile.get('features', {}).get('output_modalities', ['text']),
        }
        
        # 能力情報
        schema['capabilities'] = {
            'context_length': profile.get('capabilities', {}).get('context_length', 0),
            'max_completion_tokens': profile.get('capabilities', {}).get('max_completion_tokens', 0),
        }
        
        # tier情報
        tier_info = self.ai_loader.get_available_tiers(model_id)
        if tier_info and tier_info.get('available_tiers'):
            schema['tiers'] = tier_info
        
        # 推論設定（reasoning対応の場合）
        if profile.get('reasoning'):
            schema['reasoning'] = profile['reasoning']
        
        # ツール設定スキーマ
        schema['tools_config_schema'] = {
            'mode': {
                'type': 'string',
                'options': ['none', 'all', 'allowlist'],
                'default': 'none',
                'description': 'ツール使用モード'
            },
            'allowlist': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'mode=allowlist時に使用するツール名リスト'
            },
            'tool_choice': {
                'type': 'string',
                'options': ['auto', 'none', 'required'],
                'default': 'auto',
                'description': 'ツール選択方法'
            }
        }
        
        # 利用可能なツール一覧
        if self.tool_loader:
            schema['available_tools'] = [
                {
                    'name': tool_name,
                    'display_name': tool_info.get('name', tool_name),
                    'description': tool_info.get('description', ''),
                    'has_direct_invoke': self._has_direct_invoke(tool_name)
                }
                for tool_name, tool_info in self.tool_loader.loaded_tools.items()
            ]
        else:
            schema['available_tools'] = []
        
        # 外部ツール設定スキーマ
        schema['external_tools_schema'] = {
            'mode': {
                'type': 'string',
                'options': ['none', 'allowlist'],
                'default': 'none',
                'description': '外部ツール指示モード'
            },
            'allowlist': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': '外部ツール候補名リスト'
            },
            'instructions': {
                'type': 'string',
                'description': 'ツール使用に関する追加指示'
            }
        }
        
        # tooluse_output設定
        schema['tooluse_output_options'] = ['json', 'text']
        
        return schema
    
    def _build_parameter_schema(self, profile: Dict) -> Dict[str, Any]:
        """
        プロファイルからパラメータスキーマを構築
        
        Args:
            profile: モデルプロファイル
        
        Returns:
            パラメータスキーマ
        """
        params = {}
        
        # プロファイルに定義されたパラメータ
        if '_parameters' in profile:
            params = dict(profile['_parameters'])
        
        # サポートされているパラメータを確認
        supported = profile.get('capabilities', {}).get('supported_parameters', [])
        
        # 基本パラメータのデフォルト定義
        default_params = {
            'temperature': {
                'type': 'number',
                'description': '生成のランダム性を制御',
                'min': 0.0,
                'max': 2.0,
                'default': 0.7,
                'step': 0.1
            },
            'top_p': {
                'type': 'number',
                'description': '累積確率によるサンプリング',
                'min': 0.0,
                'max': 1.0,
                'default': 1.0
            },
            'max_tokens': {
                'type': 'integer',
                'description': '最大出力トークン数',
                'min': 1,
                'max': profile.get('capabilities', {}).get('max_completion_tokens', 4096),
                'default': 4096
            }
        }
        
        # サポートされているパラメータでデフォルト定義があるものを追加
        for param_name in supported:
            if param_name not in params and param_name in default_params:
                params[param_name] = default_params[param_name]
        
        return params
    
    def _has_direct_invoke(self, tool_name: str) -> bool:
        """
        ツールがdirect invoke用のファイルを持っているか確認
        
        Args:
            tool_name: ツール名
        
        Returns:
            direct invoke対応の場合True
        """
        if not self.tool_loader or tool_name not in self.tool_loader.loaded_tools:
            return False
        
        # tool_loader に has_direct_invoke メソッドがあるか確認
        if hasattr(self.tool_loader, 'has_direct_invoke'):
            return self.tool_loader.has_direct_invoke(tool_name)
        
        # フォールバック: 直接ファイルを確認
        tool_info = self.tool_loader.loaded_tools[tool_name]
        tool_dir = Path(tool_info.get('tool_dir', ''))
        
        if not tool_dir.exists():
            return False
        
        # direct_invoke.py または *_direct_invoke.py を探す
        if (tool_dir / 'direct_invoke.py').exists():
            return True
        
        for f in tool_dir.glob('*_direct_invoke.py'):
            return True
        
        return False
    
    def direct_invoke(
        self,
        model_id: str,
        message: str,
        provider: str = None,
        system_prompt: str = None,
        api_tier: str = None,
        params: Dict[str, Any] = None,
        tools_config: Dict[str, Any] = None,
        external_tools: Dict[str, Any] = None,
        tooluse_output: str = 'json'
    ) -> Dict[str, Any]:
        """
        Direct Invoke API - チャット履歴なしで1ターン実行
        
        Args:
            model_id: モデルID
            message: ユーザーメッセージ
            provider: プロバイダー名（指定時はmodel_idのproviderと一致チェック）
            system_prompt: システムプロンプト
            api_tier: 使用するtier
            params: 公式パラメータ
            tools_config: ツール設定 {mode, allowlist, tool_choice}
            external_tools: 外部ツール設定 {mode, allowlist, instructions}
            tooluse_output: ツール使用指示の出力形式 ('json' or 'text')
        
        Returns:
            実行結果
        """
        result = {
            'success': False,
            'response_text': None,
            'tool_uses': None,
            'used_model_id': model_id,
            'used_provider': None,
            'used_api_tier': api_tier,
            'used_params': {},
            'limits': None,
            'usage': None,
            'error': None
        }
        
        try:
            # モデルプロファイルを取得
            profile = self.ai_loader.get_model_profile(model_id)
            if not profile:
                result['error'] = f"モデル '{model_id}' が見つかりません"
                return result
            
            provider_name = profile['provider_name']
            result['used_provider'] = provider_name
            
            # プロバイダー一致チェック
            if provider and provider != provider_name:
                result['error'] = f"指定されたプロバイダー '{provider}' とモデルのプロバイダー '{provider_name}' が一致しません"
                return result
            
            # tier適用済みモデル情報を取得
            model_with_tier = self.ai_loader.get_model_with_tier(model_id, api_tier)
            if model_with_tier:
                result['limits'] = model_with_tier.get('limits')
                result['used_api_tier'] = model_with_tier.get('applied_tier')
            
            # モデルを設定
            if model_id != self.current_model_id:
                if not self.set_model(model_id):
                    result['error'] = f"モデル '{model_id}' の設定に失敗しました"
                    return result
            
            # パラメータを正規化
            normalized_params = self._normalize_invoke_params(profile, params or {})
            result['used_params'] = normalized_params
            
            # システムプロンプトを構築
            final_system_prompt = self._build_invoke_system_prompt(
                system_prompt, 
                external_tools, 
                tooluse_output
            )
            
            # ツール設定を処理
            tools = self._prepare_invoke_tools(tools_config)
            
            # 空の標準履歴を作成
            empty_history = create_standard_history()
            
            # ツール実行結果を初期化
            tool_executions = []
            
            # API呼び出し
            response = self.send_request(
                model_id=model_id,
                history=empty_history,
                current_text_input=message,
                current_file_paths=[],
                temperature=normalized_params.get('temperature', 0.7),
                thinking_budget=normalized_params.get('thinking_budget'),
                tools=tools,
                use_loaded_tools=False,  # 明示的に渡したツールのみ使用
                system_prompt=final_system_prompt
            )
            
            # 応答を処理
            response_text = self.current_client.extract_response_text(response) if self.current_client else ""
            
            # Function Callがある場合は処理
            if self._has_function_calls_in_response(response):
                response_text, tool_executions = self._handle_direct_invoke_function_calls(
                    response, model_id, empty_history, tools_config
                )
            
            # 外部ツール指示を抽出
            tool_uses = self._extract_tool_uses(response_text, external_tools, tooluse_output)
            
            result['success'] = True
            result['response_text'] = response_text
            result['tool_uses'] = tool_uses
            
            # ツール実行結果があれば追加
            if tool_executions:
                result['tool_executions'] = tool_executions
            
            # 使用量情報を取得（可能なら）
            result['usage'] = self._extract_usage(response)
            
        except Exception as e:
            result['error'] = str(e)
            print(f"Direct invoke エラー: {e}")
            traceback.print_exc()
        
        return result
    
    def _normalize_invoke_params(self, profile: Dict, params: Dict) -> Dict:
        """
        invokeパラメータを正規化
        
        Args:
            profile: モデルプロファイル
            params: 入力パラメータ
        
        Returns:
            正規化されたパラメータ
        """
        normalized = {}
        
        # プロファイルのパラメータ定義を取得
        param_defs = profile.get('_parameters', {})
        supported = profile.get('capabilities', {}).get('supported_parameters', [])
        
        for key, value in params.items():
            # サポートされているパラメータのみ受け入れ
            if key in supported or key in param_defs:
                # 数値パラメータの範囲チェック
                if key in param_defs:
                    param_def = param_defs[key]
                    if param_def.get('type') in ('number', 'integer'):
                        min_val = param_def.get('min')
                        max_val = param_def.get('max')
                        if min_val is not None and value < min_val:
                            value = min_val
                        if max_val is not None and value > max_val:
                            value = max_val
                
                normalized[key] = value
        
        # デフォルト値を適用
        defaults = profile.get('capabilities', {}).get('default_parameters', {})
        for key, default_value in defaults.items():
            if key not in normalized:
                normalized[key] = default_value
        
        return normalized
    
    def _build_invoke_system_prompt(
        self, 
        user_prompt: str, 
        external_tools: Dict, 
        tooluse_output: str
    ) -> str:
        """
        invoke用のシステムプロンプトを構築
        
        Args:
            user_prompt: ユーザー指定のシステムプロンプト
            external_tools: 外部ツール設定
            tooluse_output: ツール使用指示の出力形式
        
        Returns:
            最終的なシステムプロンプト
        """
        parts = []
        
        if user_prompt:
            parts.append(user_prompt)
        
        # 外部ツール指示を追加
        if external_tools and external_tools.get('mode') == 'allowlist':
            allowlist = external_tools.get('allowlist', [])
            instructions = external_tools.get('instructions', '')
            
            if allowlist:
                tool_list = ', '.join(allowlist)
                
                if tooluse_output == 'json':
                    parts.append(f"""
以下の外部ツールが利用可能です（直接実行はできません）: {tool_list}

これらのツールが必要な場合、応答の最後に以下のJSON形式でツール使用指示を出力してください:

```tool_uses
[{{"name": "ツール名", "args": {{"パラメータ名": "値"}}}}]
```

{instructions}
""".strip())
                else:
                    parts.append(f"""
以下の外部ツールが利用可能です（直接実行はできません）: {tool_list}

これらのツールが必要な場合、応答内で使用方法を説明してください。

{instructions}
""".strip())
        
        return '\n\n'.join(parts) if parts else None
    
    def _prepare_invoke_tools(self, tools_config: Dict) -> Optional[List]:
        """
        invoke用のツールリストを準備
        
        Args:
            tools_config: ツール設定
        
        Returns:
            ツールリスト
        """
        if not tools_config or not self.tool_loader:
            return None
        
        mode = tools_config.get('mode', 'none')
        
        if mode == 'none':
            return None
        
        if mode == 'all':
            return self.tool_loader.get_tools_for_provider(self.current_provider)
        
        if mode == 'allowlist':
            allowlist = tools_config.get('allowlist', [])
            if not allowlist:
                return None
            
            # allowlistに含まれるツールのみをフィルタ
            return self._filter_tools_for_invoke(allowlist)
        
        return None
    
    def _filter_tools_for_invoke(self, allowlist: List[str]) -> Optional[List]:
        """
        direct invoke用にツールをフィルタ
        
        Args:
            allowlist: 許可するツール名リスト
        
        Returns:
            フィルタ済みツールリスト
        """
        if not self.tool_loader:
            return None
        
        provider = self.current_provider or 'gemini'
        all_tools = self.tool_loader.get_tools_for_provider(provider)
        
        if not all_tools:
            return None
        
        # プロバイダー固有のフィルタリング
        if provider == 'gemini':
            return self._filter_gemini_tools_for_invoke(all_tools, allowlist)
        
        # 汎用フィルタリング
        return self._filter_generic_tools(all_tools, allowlist)
    
    def _filter_gemini_tools_for_invoke(self, all_tools: List, allowlist: List[str]) -> Optional[List]:
        """Gemini形式のツールをフィルタ（invoke用）"""
        try:
            from google.genai import types as gemini_types
        except ImportError:
            return None
        
        filtered_declarations = []
        
        for tool in all_tools:
            if hasattr(tool, 'function_declarations') and tool.function_declarations:
                for fd in tool.function_declarations:
                    if hasattr(fd, 'name') and fd.name in allowlist:
                        filtered_declarations.append(fd)
        
        if filtered_declarations:
            return [gemini_types.Tool(function_declarations=filtered_declarations)]
        
        return None
    
    def _has_function_calls_in_response(self, response) -> bool:
        """レスポンスにFunction Callが含まれているか確認"""
        if not hasattr(response, 'candidates') or not response.candidates:
            return False
        
        try:
            content = response.candidates[0].content
            for part in content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    return True
        except:
            pass
        
        return False
    
    def _handle_direct_invoke_function_calls(
        self, 
        response, 
        model_id: str, 
        history: Dict,
        tools_config: Dict
    ) -> tuple:
        """
        Direct invoke時のFunction Callを処理
        
        Args:
            response: AI応答
            model_id: モデルID
            history: 履歴
            tools_config: ツール設定
        
        Returns:
            (最終応答テキスト, 実行結果リスト)
        """
        if not self.current_client or not self.tool_loader:
            return self.current_client.extract_response_text(response) if self.current_client else "", []
        
        # コンテキストを作成（AgentRuntimeは含めない）
        context = {
            'execution_id': str(uuid.uuid4()),
            'tool_loader': self.tool_loader,
            'direct_invoke': True  # direct invokeフラグ
        }
        
        # Function Call処理を委譲
        try:
            final_response, executions = self.handle_function_calls(
                response, model_id, history, context
            )
            response_text = self.current_client.extract_response_text(final_response)
            return response_text, executions
        except Exception as e:
            print(f"Function Call処理エラー: {e}")
            return self.current_client.extract_response_text(response), []
    
    def _extract_tool_uses(
        self, 
        response_text: str, 
        external_tools: Dict,
        tooluse_output: str
    ) -> Optional[List[Dict]]:
        """
        応答テキストからtool_uses指示を抽出
        
        Args:
            response_text: 応答テキスト
            external_tools: 外部ツール設定
            tooluse_output: 出力形式
        
        Returns:
            tool_usesリスト
        """
        if not external_tools or external_tools.get('mode') != 'allowlist':
            return None
        
        if tooluse_output != 'json':
            return None
        
        # ```tool_uses ... ``` ブロックを探す
        import re
        pattern = r'```tool_uses\s*\n(.*?)\n```'
        matches = re.findall(pattern, response_text, re.DOTALL)
        
        if not matches:
            return None
        
        try:
            # 最後のマッチを使用
            tool_uses_json = matches[-1].strip()
            tool_uses = json.loads(tool_uses_json)
            
            if isinstance(tool_uses, list):
                return tool_uses
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _extract_usage(self, response) -> Optional[Dict]:
        """
        レスポンスから使用量情報を抽出
        
        Args:
            response: AI応答
        
        Returns:
            使用量情報
        """
        try:
            if hasattr(response, 'usage_metadata'):
                metadata = response.usage_metadata
                return {
                    'prompt_tokens': getattr(metadata, 'prompt_token_count', None),
                    'completion_tokens': getattr(metadata, 'candidates_token_count', None),
                    'total_tokens': getattr(metadata, 'total_token_count', None)
                }
        except:
            pass
        
        return None
    
    def _filter_generic_tools(self, all_tools: List, allowlist: List[str]) -> Optional[List]:
        """
        汎用的なツールフィルタリング（プロバイダー非依存）
        
        Args:
            all_tools: 全ツールのリスト
            allowlist: 許可されたツール名のリスト
        
        Returns:
            フィルタリングされたツールのリスト
        """
        filtered = []
        
        for tool in all_tools:
            tool_name = None
            
            if isinstance(tool, dict):
                tool_name = (
                    tool.get('name') or 
                    tool.get('function', {}).get('name') or
                    tool.get('function_name')
                )
            elif hasattr(tool, 'name'):
                tool_name = tool.name
            elif hasattr(tool, 'function_declarations'):
                for fd in tool.function_declarations:
                    fd_name = fd.name if hasattr(fd, 'name') else fd.get('name') if isinstance(fd, dict) else None
                    if fd_name and fd_name in allowlist:
                        filtered.append(fd)
                continue
            
            if tool_name and tool_name in allowlist:
                filtered.append(tool)
        
        return filtered if filtered else None