# tool/tool_loader.py
"""
tool/[toolname]/ディレクトリからツールを動的に読み込むシステム
"""

import importlib.util
import sys
import subprocess
import os
import json
import socket
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading
import queue
import platform

# フォールバックインポート対応
try:
    from tool_dependency_manager import ToolDependencyManager
except ImportError:
    try:
        from tool.tool_dependency_manager import ToolDependencyManager
    except ImportError:
        # 最終フォールバック: 相対パスで直接読み込み
        import importlib.util as _imp_util
        _dep_path = Path(__file__).parent / "tool_dependency_manager.py"
        if _dep_path.exists():
            _spec = _imp_util.spec_from_file_location("tool_dependency_manager", _dep_path)
            _module = _imp_util.module_from_spec(_spec)
            _spec.loader.exec_module(_module)
            ToolDependencyManager = _module.ToolDependencyManager
        else:
            # ToolDependencyManager が見つからない場合のダミークラス
            class ToolDependencyManager:
                def __init__(self, base_dir):
                    self.base_dir = base_dir
                def get_venv_python(self, name): return None
                def create_venv(self, name): return False
                def check_and_install(self, name): return True
                def add_venv_to_path(self, name): return False


class ToolLoader:
    def __init__(self, tools_dir: Path = None):
        """
        ツールローダーを初期化
        
        Args:
            tools_dir: ツールが格納されているディレクトリ
        """
        if tools_dir is None:
            # エコシステム経由でパス解決を試みる
            try:
                from backend_core.ecosystem.compat import get_tools_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    tools_dir = get_tools_dir()
                else:
                    tools_dir = Path(__file__).parent
            except ImportError:
                tools_dir = Path(__file__).parent
        
        self.tools_dir = Path(tools_dir)
        self.loaded_tools: Dict[str, Dict[str, Any]] = {}
        self.tool_ports: Dict[str, int] = {}
        self.base_port = 6000
        self.message_queue = queue.Queue()
        
        # ツール設定管理
        self.settings_file = self.tools_dir / "userdata" / "tool_settings.json"
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.tool_settings = self._load_settings()
        
        # 依存関係マネージャー
        self.dependency_manager = ToolDependencyManager(self.tools_dir)

    def _load_settings(self) -> dict:
        """ツール設定を読み込む"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"設定ファイル読み込みエラー: {e}")
        return {}

    def _save_settings(self):
        """ツール設定を保存"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.tool_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定ファイル保存エラー: {e}")

    def _find_free_port(self, start_port: int = 6000) -> int:
        """空いているポートを見つける"""
        port = start_port
        while port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('', port))
                    return port
                except:
                    port += 1
        raise RuntimeError("利用可能なポートが見つかりません")

    def load_all_tools(self) -> None:
        """tool/内のすべてのツールフォルダを読み込む"""
        if not self.tools_dir.exists():
            print(f"警告: ツールディレクトリが存在しません: {self.tools_dir}")
            self.tools_dir.mkdir(parents=True, exist_ok=True)
            return
        
        print("\n=== Tool Loader: ツールの読み込みを開始 ===")
            
        # tool/内の各ディレクトリを確認
        for tool_dir in self.tools_dir.iterdir():
            if tool_dir.is_dir() and not tool_dir.name.startswith('.') and not tool_dir.name.startswith('_'):
                if tool_dir.name == 'userdata':
                    continue
                self._load_tool_from_directory(tool_dir)
        
        print(f"\n=== 読み込み完了: {len(self.loaded_tools)}個のツール ===")

    def _load_tool_from_directory(self, tool_dir: Path) -> None:
        """特定のツールディレクトリからツールを読み込む"""
        print(f"\nツールディレクトリを処理中: {tool_dir.name}")
        
        # 依存関係マネージャーを使用
        requirements_file = tool_dir / "requirements.txt"
        if requirements_file.exists():
            print(f"  requirements.txt を検出しました")
            if not self.dependency_manager.check_and_install(tool_dir.name):
                print(f"  警告: 依存関係のインストールに失敗しました")
                # エラーでも読み込みを試みる
        
        # ツールファイルを読み込む
        tool_files = list(tool_dir.glob("*_tool.py"))
        
        for tool_file in tool_files:
            try:
                self._load_tool_file(tool_file, tool_dir)
            except Exception as e:
                print(f"ツール読み込みエラー ({tool_file.name}): {e}")
                import traceback
                traceback.print_exc()

    def _detect_direct_invoke_file(self, tool_dir: Path) -> Optional[Path]:
        """
        ツールディレクトリ内のdirect invoke用ファイルを検出
        
        検出優先順位:
        1. direct_invoke.py
        2. *_direct_invoke.py（最初に見つかったもの）
        
        Args:
            tool_dir: ツールディレクトリのパス
        
        Returns:
            direct invokeファイルのパス（存在しない場合はNone）
        """
        # 1. direct_invoke.py を探す
        direct_invoke_file = tool_dir / "direct_invoke.py"
        if direct_invoke_file.exists():
            return direct_invoke_file
        
        # 2. *_direct_invoke.py を探す
        for f in tool_dir.glob("*_direct_invoke.py"):
            if f.is_file():
                return f
        
        return None

    def _load_tool_file(self, file_path: Path, tool_dir: Path) -> None:
        """個別のツールファイルを読み込む"""
        module_name = f"tool_{tool_dir.name}_{file_path.stem}"
        
        # 依存関係マネージャーを使用
        tool_venv_python = self.dependency_manager.get_venv_python(tool_dir.name)
        
        # 仮想環境のsite-packagesをパスに追加
        if tool_venv_python:
            self.dependency_manager.add_venv_to_path(tool_dir.name)
        
        # モジュールを読み込む
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # 必要な属性の確認
        required_attrs = ["TOOL_NAME", "TOOL_DESCRIPTION", "get_function_declaration", "execute", "TOOL_ICON"]
        for attr in required_attrs:
            if not hasattr(module, attr):
                raise ValueError(f"{file_path.name}に必須属性 '{attr}' がありません")
        
        # UI情報を取得（get_ui_info関数があれば）
        ui_info = {}
        if hasattr(module, 'get_ui_info'):
            ui_info = module.get_ui_info()
        
        # index.htmlの存在確認（デフォルト）
        has_ui = (tool_dir / "index.html").exists()
        html_file = "index.html"
        
        # get_ui_infoがあればそれを優先
        if ui_info:
            has_ui = ui_info.get('has_ui', has_ui)
            html_file = ui_info.get('html_file', html_file)
        
        # ツール情報を保存
        function_decl = module.get_function_declaration()
        tool_key = function_decl["name"]
        
        # 重複チェック
        if tool_key in self.loaded_tools:
            print(f"  ⚠️ 警告: 関数名 '{tool_key}' が既に存在します。")
            print(f"    既存: {self.loaded_tools[tool_key]['file_path']}")
            print(f"    新規: {file_path}")
            
            # ユニークな名前を生成（ディレクトリ名を接頭辞として追加）
            unique_tool_key = f"{tool_dir.name}_{tool_key}"
            print(f"    → '{unique_tool_key}' として登録します")
            
            # function_declarationの名前も更新
            function_decl["name"] = unique_tool_key
            tool_key = unique_tool_key
        
        # 設定スキーマを取得（存在する場合）
        settings_schema = None
        if hasattr(module, 'get_settings_schema'):
            settings_schema = module.get_settings_schema()
            
            # デフォルト設定を初期化
            if tool_key not in self.tool_settings:
                self.tool_settings[tool_key] = {}
                if settings_schema:
                    for key, config in settings_schema.items():
                        self.tool_settings[tool_key][key] = config.get('default')
                self._save_settings()
        
        # direct invoke用ファイルの検出
        direct_invoke_file = self._detect_direct_invoke_file(tool_dir)
        has_direct_invoke = direct_invoke_file is not None
        
        self.loaded_tools[tool_key] = {
            "module": module,
            "name": module.TOOL_NAME,
            "description": module.TOOL_DESCRIPTION,
            "icon": module.TOOL_ICON,
            "function_declaration": function_decl,
            "execute": module.execute,
            "file_path": str(file_path),
            "tool_dir": str(tool_dir),
            "has_ui": has_ui,
            "html_file": html_file,
            "has_venv": tool_venv_python is not None,
            "venv_python": tool_venv_python,
            "port": None,
            "settings_schema": settings_schema,
            "enabled": True,
            "has_direct_invoke": has_direct_invoke,
            "direct_invoke_file": str(direct_invoke_file) if direct_invoke_file else None
        }
        
        direct_status = "（direct invoke対応）" if has_direct_invoke else ""
        venv_status = "（専用仮想環境使用）" if tool_venv_python else ""
        print(f"  ✓ ツール読み込み成功: {module.TOOL_NAME} ({tool_key}) {venv_status}{direct_status}")

    def _load_direct_invoke_module(self, tool_name: str, direct_invoke_file: Path) -> Optional[Any]:
        """
        direct invoke用モジュールを読み込む
        
        Args:
            tool_name: ツール名
            direct_invoke_file: direct invokeファイルのパス
        
        Returns:
            読み込まれたモジュール（失敗時はNone）
        """
        try:
            module_name = f"tool_{tool_name}_direct_invoke"
            
            # 依存関係マネージャーを使用して仮想環境のパスを追加
            if self.dependency_manager:
                self.dependency_manager.add_venv_to_path(tool_name)
            
            spec = importlib.util.spec_from_file_location(module_name, direct_invoke_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 必須関数の確認
            if not hasattr(module, 'execute'):
                print(f"    警告: direct_invokeモジュールに execute 関数がありません: {direct_invoke_file}")
                return None
            
            return module
            
        except Exception as e:
            print(f"    警告: direct_invokeモジュールの読み込みに失敗: {e}")
            return None

    def has_direct_invoke(self, tool_name: str) -> bool:
        """
        ツールがdirect invoke用ファイルを持っているか確認
        
        Args:
            tool_name: ツール名（function name）
        
        Returns:
            direct invoke対応の場合True
        """
        if tool_name not in self.loaded_tools:
            return False
        
        tool_info = self.loaded_tools[tool_name]
        return tool_info.get('has_direct_invoke', False)

    def execute_direct_invoke(
        self, 
        function_name: str, 
        args: dict, 
        context: dict
    ) -> dict:
        """
        direct invoke用のツール実行
        
        通常のexecuteとは異なり、direct_invoke.py が存在する場合はそちらを優先使用する。
        direct_invoke.py が存在しない場合は通常のexecuteにフォールバック。
        
        Args:
            function_name: 関数名（ツール名）
            args: 引数
            context: 実行コンテキスト
        
        Returns:
            実行結果
        """
        if function_name not in self.loaded_tools:
            return {
                "success": False,
                "error": f"ツール '{function_name}' が見つかりません"
            }
        
        tool_info = self.loaded_tools[function_name]
        tool_dir = Path(tool_info.get('tool_dir', ''))
        
        # direct invoke用ファイルを検出
        direct_invoke_file = self._detect_direct_invoke_file(tool_dir)
        
        if direct_invoke_file:
            # direct invokeモジュールを使用
            return self._execute_with_direct_invoke(
                function_name, 
                args, 
                context, 
                tool_info, 
                direct_invoke_file
            )
        else:
            # 通常のexecuteにフォールバック
            return self.execute_tool(function_name, args, context)

    def _execute_with_direct_invoke(
        self,
        function_name: str,
        args: dict,
        context: dict,
        tool_info: dict,
        direct_invoke_file: Path
    ) -> dict:
        """
        direct invoke用モジュールでツールを実行
        
        Args:
            function_name: 関数名
            args: 引数
            context: 実行コンテキスト
            tool_info: ツール情報
            direct_invoke_file: direct invokeファイルのパス
        
        Returns:
            実行結果
        """
        try:
            # モジュールを読み込み
            module = self._load_direct_invoke_module(function_name, direct_invoke_file)
            
            if not module:
                # 読み込み失敗時は通常のexecuteにフォールバック
                print(f"    direct_invokeモジュールの読み込みに失敗、通常のexecuteを使用: {function_name}")
                return self.execute_tool(function_name, args, context)
            
            # 強制停止イベントを取得
            abort_event = context.get('abort_event')
            
            # 実行前チェック
            if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                return {
                    "success": False,
                    "error": "実行が中断されました",
                    "aborted": True
                }
            
            # 設定を取得
            tool_settings = self.tool_settings.get(function_name, {})
            
            # コンテキスト情報を追加
            enhanced_context = {
                **context,
                "tool_dir": str(tool_info["tool_dir"]),
                "settings": tool_settings,
                "has_venv": tool_info.get("has_venv", False),
                "venv_python": tool_info.get("venv_python"),
                "abort_event": abort_event,
                "direct_invoke": True,  # direct invokeフラグ
                "message_callback": lambda msg: self._handle_tool_message(
                    msg, context, function_name, tool_info
                )
            }
            
            # direct invoke用executeを実行
            print(f"ツール {function_name} をdirect invokeモードで実行中...")
            result = module.execute(args, enhanced_context)
            
            # 実行後チェック
            if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                if isinstance(result, dict):
                    result['aborted'] = True
                else:
                    result = {
                        "success": False,
                        "result": result,
                        "aborted": True
                    }
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"direct invokeツール実行エラー: {str(e)}"
            }

    def get_tool_info_for_invoke_schema(self) -> List[Dict[str, Any]]:
        """
        invoke_schema用のツール情報を取得
        
        Returns:
            ツール情報のリスト
        """
        tools_info = []
        
        for tool_name, tool_info in self.loaded_tools.items():
            tools_info.append({
                'name': tool_name,
                'display_name': tool_info.get('name', tool_name),
                'description': tool_info.get('description', ''),
                'icon': tool_info.get('icon', ''),
                'has_direct_invoke': tool_info.get('has_direct_invoke', False),
                'has_ui': tool_info.get('has_ui', False),
                'enabled': tool_info.get('enabled', True)
            })
        
        return tools_info

    def _convert_type(self, type_str: str) -> Any:
        """文字列型をプロバイダー固有の型に変換（現在はGemini用）"""
        # プロバイダー別の変換はget_tools_for_providerで行う
        return type_str

    def get_tools_for_provider(self, provider_name: str = "gemini") -> List[Any]:
        """指定されたプロバイダー用のツールリストを生成"""
        if not self.loaded_tools:
            return []
        
        # プロバイダーごとの変換処理
        if provider_name == "gemini":
            from google.genai import types
            
            seen_names = set()
            function_declarations = []
            
            for tool_name, tool_info in self.loaded_tools.items():
                # 無効化されているツールはスキップ
                if not tool_info.get("enabled", True):
                    continue
                
                decl = tool_info["function_declaration"]
                
                if decl["name"] in seen_names:
                    print(f"警告: 重複した関数名をスキップ: {decl['name']} (from {tool_name})")
                    continue
                
                seen_names.add(decl["name"])
                
                # Gemini用の型変換
                type_mapping = {
                    "string": types.Type.STRING,
                    "integer": types.Type.INTEGER,
                    "number": types.Type.NUMBER,
                    "boolean": types.Type.BOOLEAN,
                    "array": types.Type.ARRAY,
                    "object": types.Type.OBJECT
                }
                
                # パラメータのプロパティを変換
                properties = {}
                for key, value in decl["parameters"].get("properties", {}).items():
                    prop_type = type_mapping.get(value.get("type", "string"), types.Type.STRING)
                    
                    # 配列型の場合、itemsスキーマも必要
                    if prop_type == types.Type.ARRAY:
                        items_type = value.get("items", {}).get("type", "string")
                        properties[key] = types.Schema(
                            type=prop_type,
                            description=value.get("description", ""),
                            items=types.Schema(type=type_mapping.get(items_type, types.Type.STRING))
                        )
                    else:
                        properties[key] = types.Schema(
                            type=prop_type,
                            description=value.get("description", "")
                        )
                
                # Gemini用のFunctionDeclarationオブジェクトを作成
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=decl["name"],
                        description=decl["description"],
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            required=decl["parameters"].get("required", []),
                            properties=properties
                        )
                    )
                )
            
            print(f"読み込まれたツール関数: {len(function_declarations)}個 - {', '.join(seen_names)}")
            return [types.Tool(function_declarations=function_declarations)] if function_declarations else []
        
        elif provider_name == "openai":
            # OpenAI形式への変換
            tools = []
            for tool_name, tool_info in self.loaded_tools.items():
                if not tool_info.get("enabled", True):
                    continue
                decl = tool_info["function_declaration"]
                tools.append({
                    "type": "function",
                    "function": {
                        "name": decl["name"],
                        "description": decl["description"],
                        "parameters": decl["parameters"]
                    }
                })
            return tools
        
        elif provider_name == "anthropic":
            # Anthropic形式への変換
            tools = []
            for tool_name, tool_info in self.loaded_tools.items():
                if not tool_info.get("enabled", True):
                    continue
                decl = tool_info["function_declaration"]
                tools.append({
                    "name": decl["name"],
                    "description": decl["description"],
                    "input_schema": decl["parameters"]
                })
            return tools
        
        # デフォルト（標準形式）
        return []

    def execute_tool(self, function_name: str, args: dict, context: dict) -> dict:
        """
        指定されたツールを実行（強制停止対応強化）
        """
        if function_name not in self.loaded_tools:
            return {
                "success": False,
                "error": f"ツール '{function_name}' が見つかりません"
            }
        
        try:
            tool_info = self.loaded_tools[function_name]
            
            # 強制停止イベントを取得
            abort_event = context.get('abort_event')
            
            # 実行前チェック
            if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                print(f"ツール {function_name} は実行前に中断されました")
                return {
                    "success": False,
                    "error": "実行が中断されました",
                    "aborted": True
                }
            
            # 設定を取得
            tool_settings = self.tool_settings.get(function_name, {})
            
            # コンテキスト情報を追加
            enhanced_context = {
                **context,
                "tool_dir": tool_info["tool_dir"],
                "settings": tool_settings,
                "has_venv": tool_info["has_venv"],
                "venv_python": tool_info["venv_python"],
                "abort_event": abort_event,
                "message_callback": lambda msg: self._handle_tool_message(msg, context, function_name, tool_info)
            }
            
            # AgentRuntime をコンテキストに含める（存在する場合）
            if 'runtime' in context:
                enhanced_context['runtime'] = context['runtime']
            
            # ツールを実行
            print(f"ツール {function_name} を実行中...")
            result = tool_info["execute"](args, enhanced_context)
            
            # 実行後チェック
            if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                print(f"ツール {function_name} は実行後に中断されました")
                if isinstance(result, dict):
                    result['aborted'] = True
                else:
                    result = {
                        "success": False,
                        "result": result,
                        "aborted": True
                    }
            
            # ファイルパスを絶対パスに変換
            if isinstance(result, dict) and "files" in result and result["files"]:
                for file_info in result["files"]:
                    if "path" in file_info:
                        file_path = Path(file_info["path"])
                        
                        # 絶対パスかどうかチェック
                        if not file_path.is_absolute():
                            # 相対パスの場合、ツールディレクトリからの絶対パスに変換
                            file_path = Path(tool_info["tool_dir"]) / file_path
                        
                        # resolve() は使わず、absolute() のみ使用
                        file_info["path"] = str(file_path.absolute())
            
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"ツール実行エラー: {str(e)}"
            }

    def _handle_tool_message(self, msg: str, context: dict, function_name: str, tool_info: dict):
        """
        ツールからのメッセージを処理
        メッセージキューへの送信とUI履歴への保存を行う
        """
        # メッセージデータを構築
        message_data = {
            "type": "tool_progress",
            "tool": function_name,
            "tool_name": tool_info["name"],
            "message": msg,
            "timestamp": time.time()
        }
        
        # 実行IDがコンテキストにあれば追加
        if 'execution_id' in context:
            message_data['execution_id'] = context['execution_id']
        
        # メッセージキューに送信（リアルタイム表示用）
        self.message_queue.put(message_data)
        
        # UI履歴に直接保存
        if 'chat_id' in context and 'chat_manager' in context:
            try:
                context['chat_manager'].append_tool_log(context['chat_id'], message_data)
                print(f"[Saved to ui_history] {msg}")
            except Exception as e:
                print(f"Failed to save tool progress: {e}")
        else:
            print(f"[Warning] chat_id or chat_manager not in context, progress not saved: {msg}")

    def get_tool_messages(self) -> List[dict]:
        """キューからツールメッセージを取得"""
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def get_tool_settings(self, tool_name: str) -> dict:
        """特定のツールの設定を取得"""
        return self.tool_settings.get(tool_name, {})

    def update_tool_settings(self, tool_name: str, settings: dict) -> bool:
        """ツールの設定を更新"""
        try:
            if tool_name not in self.tool_settings:
                self.tool_settings[tool_name] = {}
            self.tool_settings[tool_name].update(settings)
            self._save_settings()
            return True
        except Exception as e:
            print(f"設定更新エラー: {e}")
            return False

    def get_all_tools_with_settings(self) -> dict:
        """すべてのツールと設定スキーマを取得"""
        result = {}
        
        # 現在読み込まれているツール
        for tool_name, tool_info in self.loaded_tools.items():
            result[tool_name] = {
                "name": tool_info["name"],
                "description": tool_info["description"],
                "icon": tool_info["icon"],
                "has_ui": tool_info["has_ui"],
                "html_file": tool_info.get("html_file", "index.html"),
                "settings_schema": tool_info.get("settings_schema"),
                "current_settings": self.tool_settings.get(tool_name, {}),
                "is_loaded": True,
                "enabled": tool_info.get("enabled", True),
                "has_direct_invoke": tool_info.get("has_direct_invoke", False)
            }
        
        # 設定は保存されているが読み込まれていないツール
        for tool_name in self.tool_settings:
            if tool_name not in result:
                result[tool_name] = {
                    "name": tool_name,
                    "description": "（ツールが見つかりません）",
                    "icon": "",
                    "has_ui": False,
                    "html_file": "index.html",
                    "settings_schema": None,
                    "current_settings": self.tool_settings[tool_name],
                    "is_loaded": False,
                    "enabled": False,
                    "has_direct_invoke": False
                }
        
        return result

    def get_available_tools(self) -> List[Dict[str, str]]:
        """利用可能なツールのリストを取得"""
        return [
            {
                "function_name": func_name,
                "display_name": info["name"],
                "description": info["description"],
                "file_path": info["file_path"],
                "enabled": info.get("enabled", True),
                "has_direct_invoke": info.get("has_direct_invoke", False)
            }
            for func_name, info in self.loaded_tools.items()
        ]

    def set_tool_enabled(self, tool_name: str, enabled: bool) -> bool:
        """ツールの有効/無効を設定"""
        if tool_name in self.loaded_tools:
            self.loaded_tools[tool_name]["enabled"] = enabled
            return True
        return False

    def reload_all_tools(self) -> dict:
        """すべてのツールを再読み込み"""
        print("\n=== ツールの再読み込みを開始 ===")
        
        # 既存のツールをクリア
        self.loaded_tools.clear()
        self.tool_ports.clear()
        self.base_port = 6000
        
        # sys.pathから追加したsite-packagesを削除
        paths_to_remove = []
        for path in sys.path:
            if ".venv" in path and str(self.tools_dir) in path:
                paths_to_remove.append(path)
        for path in paths_to_remove:
            sys.path.remove(path)
        
        # モジュールキャッシュをクリア
        modules_to_remove = []
        for module_name in sys.modules:
            if module_name.startswith('tool_'):
                modules_to_remove.append(module_name)
        for module_name in modules_to_remove:
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        # ツールを再読み込み
        self.load_all_tools()
        
        loaded_count = len(self.loaded_tools)
        print(f"\n=== 再読み込み完了: {loaded_count}個のツール ===")
        
        return {
            "success": True,
            "loaded_count": loaded_count,
            "tools": self.get_available_tools()
        }
