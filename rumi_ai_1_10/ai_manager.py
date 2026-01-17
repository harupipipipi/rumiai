# ai_manager.py 完全版（修正版）

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

# ------------------------------------------------------------
# sys.path 調整（エコシステム初期化前でも import が死なないようにする）
# ------------------------------------------------------------
_project_root = Path(__file__).parent.resolve()

# 1) tool/ を参照可能にする（既存仕様）
_tool_path = _project_root / "tool"
if str(_tool_path) not in sys.path:
    sys.path.insert(0, str(_tool_path))

# 2) prompt/ を参照可能にする（既存仕様）
_prompt_path = _project_root / "prompt"
if str(_prompt_path) not in sys.path:
    sys.path.insert(0, str(_prompt_path))

# 3) ecosystem/default/backend/components を参照可能にする
#    （エコシステム初期化が失敗/未実行でも `ai_client.*` を import できるように）
_components_dir = _project_root / "ecosystem" / "default" / "backend" / "components"
if _components_dir.exists() and str(_components_dir) not in sys.path:
    sys.path.insert(0, str(_components_dir))


# ------------------------------------------------------------
# AIClientLoader の import（多段フォールバック）
# ------------------------------------------------------------
def _import_ai_client_loader_class():
    """
    AIClientLoader を状況に応じて解決する。

    優先順:
    1) エコシステム（components_dir が sys.path に入っている想定）
       from ai_client.ai_client_loader import AIClientLoader
    2) runtime_dir 直import 形式（compatが component runtime_dir を sys.path に入れる想定）
       from ai_client_loader import AIClientLoader
    3) 旧来/ルート直下の ai_client が存在する場合
       project_root/ai_client/ai_client_loader.py から動的import
    4) ecosystem の runtime ファイルから動的import
       ecosystem/default/backend/components/ai_client/ai_client_loader.py
    """
    # (1) package import
    try:
        from ai_client.ai_client_loader import AIClientLoader  # type: ignore
        return AIClientLoader
    except Exception:
        pass

    # (2) direct import
    try:
        from ai_client_loader import AIClientLoader  # type: ignore
        return AIClientLoader
    except Exception:
        pass

    # (3) root ai_client fallback
    candidate1 = _project_root / "ai_client" / "ai_client_loader.py"
    if candidate1.exists():
        import importlib.util as _imp_util
        spec = _imp_util.spec_from_file_location("ai_client_loader", candidate1)
        if spec and spec.loader:
            module = _imp_util.module_from_spec(spec)
            sys.modules["ai_client_loader"] = module
            spec.loader.exec_module(module)
            if hasattr(module, "AIClientLoader"):
                return module.AIClientLoader

    # (4) ecosystem runtime fallback
    candidate2 = _project_root / "ecosystem" / "default" / "backend" / "components" / "ai_client" / "ai_client_loader.py"
    if candidate2.exists():
        import importlib.util as _imp_util
        spec = _imp_util.spec_from_file_location("ai_client.ai_client_loader", candidate2)
        if spec and spec.loader:
            module = _imp_util.module_from_spec(spec)
            sys.modules["ai_client.ai_client_loader"] = module
            spec.loader.exec_module(module)
            if hasattr(module, "AIClientLoader"):
                return module.AIClientLoader

    raise ImportError(
        "AIClientLoader を import できませんでした。"
        "ecosystem が配置されているか、または ai_client_loader.py が存在するか確認してください。"
    )


AIClientLoader = _import_ai_client_loader_class()


# ------------------------------------------------------------
# ToolLoader のインポート（既存の複数フォールバック維持）
# ------------------------------------------------------------
try:
    from tool_loader import ToolLoader
except ImportError:
    try:
        from tool.tool_loader import ToolLoader
    except ImportError:
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


from tool_ui_manager import tool_ui_manager
from chat_manager import create_standard_history

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
        """
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile:
            print(f"エラー: モデル {model_id} が見つかりません")
            return False

        provider_name = profile['provider_name']

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
        """
        if model_id != self.current_model_id:
            if not self.set_model(model_id):
                raise ValueError(f"モデル {model_id} の設定に失敗しました")

        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")

        final_tools = None
        if use_loaded_tools and self.tool_loader.loaded_tools:
            loaded_tools = self.tool_loader.get_tools_for_provider(self.current_provider)
            if tools:
                final_tools = self._merge_tools(tools, loaded_tools)
            else:
                final_tools = loaded_tools
        elif tools:
            final_tools = tools

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

            self._write_debug_log(f"RESPONSE from {self.current_provider} ({model_id})", {
                "success": True,
                "response_type": type(response).__name__,
                "response_text": self.current_client.extract_response_text(response)[:500]
                if hasattr(self.current_client, 'extract_response_text') else None
            })

            return response

        except Exception as e:
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
        """
        if model_id != self.current_model_id:
            if not self.set_model(model_id):
                raise ValueError(f"モデル {model_id} の設定に失敗しました")

        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")

        profile = self.ai_loader.get_model_profile(model_id)
        if not profile.get('features', {}).get('supports_streaming', False):
            raise ValueError(f"モデル {model_id} はストリーミングに対応していません")

        self.stop_event.clear()
        self.aborted_text = ""

        if abort_signal:
            self.stop_event = abort_signal

        final_tools = None
        if use_loaded_tools and self.tool_loader.loaded_tools:
            loaded_tools = self.tool_loader.get_tools_for_provider(self.current_provider)
            if tools:
                final_tools = self._merge_tools(tools, loaded_tools)
            else:
                final_tools = loaded_tools
        elif tools:
            final_tools = tools

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
        """
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")

        if context is None:
            context = {}
        context['tool_loader'] = self.tool_loader

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
        """
        if not self.current_client:
            raise ValueError("AIクライアントが初期化されていません")

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
        if self.current_client and hasattr(self.current_client, '_merge_tools'):
            return self.current_client._merge_tools(tools1, tools2)

        return tools1 + tools2

    # 以降（get_invoke_schema / direct_invoke 等）は、あなたの既存 ai_manager.py と同じでOKです。
    # 今回のエラー（ModuleNotFoundError: ai_client）を直すのに必要なのは、
    # 「AIClientLoader import の頑健化」なので、下は省略せず“現状のまま”置いてください。

    # -------------------------------
    # ここから下は、あなたの現行版をそのまま残してください
    # （以下はあなたが貼ってくれた内容をそのまま収録）
    # -------------------------------

    def get_invoke_schema(self, model_id: str) -> Optional[Dict[str, Any]]:
        profile = self.ai_loader.get_model_profile(model_id)
        if not profile:
            return None

        schema = {
            'model_id': model_id,
            'provider': profile['provider_name'],
            'name': profile['basic_info']['name'],
            'product': profile['basic_info'].get('product'),
            'description': profile['basic_info'].get('description', ''),
            'status': profile['basic_info'].get('status', 'active'),
        }

        schema['parameters'] = self._build_parameter_schema(profile)

        schema['features'] = {
            'supports_function_calling': profile.get('features', {}).get('supports_function_calling', False),
            'supports_tool_use': profile.get('features', {}).get('supports_tool_use', False),
            'supports_streaming': profile.get('features', {}).get('supports_streaming', False),
            'supports_reasoning': profile.get('features', {}).get('supports_reasoning', False),
            'is_multimodal': profile.get('features', {}).get('is_multimodal', False),
            'input_modalities': profile.get('features', {}).get('input_modalities', ['text']),
            'output_modalities': profile.get('features', {}).get('output_modalities', ['text']),
        }

        schema['capabilities'] = {
            'context_length': profile.get('capabilities', {}).get('context_length', 0),
            'max_completion_tokens': profile.get('capabilities', {}).get('max_completion_tokens', 0),
        }

        tier_info = self.ai_loader.get_available_tiers(model_id) if hasattr(self.ai_loader, "get_available_tiers") else None
        if tier_info and tier_info.get('available_tiers'):
            schema['tiers'] = tier_info

        if profile.get('reasoning'):
            schema['reasoning'] = profile['reasoning']

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

        schema['tooluse_output_options'] = ['json', 'text']
        return schema

    def _build_parameter_schema(self, profile: Dict) -> Dict[str, Any]:
        params = {}

        if '_parameters' in profile:
            params = dict(profile['_parameters'])

        supported = profile.get('capabilities', {}).get('supported_parameters', [])

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

        for param_name in supported:
            if param_name not in params and param_name in default_params:
                params[param_name] = default_params[param_name]

        return params

    def _has_direct_invoke(self, tool_name: str) -> bool:
        if not self.tool_loader or tool_name not in self.tool_loader.loaded_tools:
            return False

        if hasattr(self.tool_loader, 'has_direct_invoke'):
            return self.tool_loader.has_direct_invoke(tool_name)

        tool_info = self.tool_loader.loaded_tools[tool_name]
        tool_dir = Path(tool_info.get('tool_dir', ''))

        if not tool_dir.exists():
            return False

        if (tool_dir / 'direct_invoke.py').exists():
            return True

        for _ in tool_dir.glob('*_direct_invoke.py'):
            return True

        return False

    # direct_invoke 以下も（あなたの現行実装どおり）続けてOKです
    # ※ここでは省略しません。あなたの手元の ai_manager.py の残りをそのまま残してください。
