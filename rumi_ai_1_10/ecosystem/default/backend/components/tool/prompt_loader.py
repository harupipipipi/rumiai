# ecosystem/default/backend/components/prompt/prompt_loader.py
"""
プロンプトの動的読み込みシステム
prompt/[prompt_name]/ディレクトリからプロンプトを動的に読み込む
"""

import importlib.util
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# PromptDependencyManager のインポート
# 同じディレクトリ（runtime_dir）にあるので直接インポート可能
try:
    from prompt_dependency_manager import PromptDependencyManager
except ImportError:
    # フォールバック: 同じディレクトリから直接読み込み
    import importlib.util as _imp_util
    _dep_path = Path(__file__).parent / "prompt_dependency_manager.py"
    if _dep_path.exists():
        _spec = _imp_util.spec_from_file_location("prompt_dependency_manager", _dep_path)
        _module = _imp_util.module_from_spec(_spec)
        sys.modules["prompt_dependency_manager"] = _module
        _spec.loader.exec_module(_module)
        PromptDependencyManager = _module.PromptDependencyManager
    else:
        # PromptDependencyManager が見つからない場合のダミークラス
        class PromptDependencyManager:
            def __init__(self, base_dir):
                self.base_dir = base_dir
            def get_venv_python(self, name): return None
            def create_venv(self, name): return False
            def check_and_install(self, name): return True
            def add_venv_to_path(self, name): return False


class PromptLoader:
    """プロンプトを動的に読み込むローダー"""
    
    def __init__(self, prompt_dir: Path = None):
        """
        プロンプトローダーを初期化
        
        Args:
            prompt_dir: プロンプトが格納されているディレクトリ
        """
        if prompt_dir is None:
            # エコシステム経由でパス解決を試みる
            try:
                from backend_core.ecosystem.compat import get_prompts_assets_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    prompt_dir = get_prompts_assets_dir()
                else:
                    prompt_dir = Path(__file__).parent
            except ImportError:
                prompt_dir = Path(__file__).parent
        
        self.prompt_dir = Path(prompt_dir)
        self.loaded_prompts: Dict[str, Dict[str, Any]] = {}
        
        # 設定管理
        self.settings_file = self.prompt_dir / "userdata" / "prompt_settings.json"
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.prompt_settings = self._load_settings()
        
        # 依存関係マネージャー
        self.dependency_manager = PromptDependencyManager(self.prompt_dir)
    
    def _load_settings(self) -> dict:
        """プロンプト設定を読み込む"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"設定ファイル読み込みエラー: {e}")
        return {}
    
    def _save_settings(self):
        """プロンプト設定を保存"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.prompt_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定ファイル保存エラー: {e}")
    
    def load_all_prompts(self) -> None:
        """prompt/内のすべてのプロンプトフォルダを読み込む"""
        if not self.prompt_dir.exists():
            print(f"警告: プロンプトディレクトリが存在しません: {self.prompt_dir}")
            self.prompt_dir.mkdir(parents=True, exist_ok=True)
            return
        
        print("\n=== Prompt Loader: プロンプトの読み込みを開始 ===")
        
        # prompt/内の各ディレクトリを確認
        for item in self.prompt_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                if item.name == 'userdata':
                    continue
                self._load_prompt_from_directory(item)
        
        print(f"\n=== 読み込み完了: {len(self.loaded_prompts)}個のプロンプト ===")
    
    def _load_prompt_from_directory(self, prompt_dir: Path) -> None:
        """特定のプロンプトディレクトリからプロンプトを読み込む"""
        prompt_name = prompt_dir.name
        print(f"\nプロンプトディレクトリを処理中: {prompt_name}")
        
        # requirements.txtが存在する場合は仮想環境をセットアップ
        requirements_file = prompt_dir / "requirements.txt"
        if requirements_file.exists():
            print(f"  requirements.txt を検出しました")
            if not self.dependency_manager.check_and_install(prompt_name):
                print(f"  警告: 依存関係のインストールに失敗しました")
        
        # プロンプトファイルを探す (*_prompt.py)
        prompt_files = list(prompt_dir.glob("*_prompt.py"))
        
        for prompt_file in prompt_files:
            try:
                self._load_prompt_file(prompt_file, prompt_dir)
            except Exception as e:
                print(f"  プロンプト読み込みエラー ({prompt_file.name}): {e}")
                import traceback
                traceback.print_exc()
    
    def _load_prompt_file(self, file_path: Path, prompt_dir: Path) -> None:
        """個別のプロンプトファイルを読み込む"""
        module_name = f"prompt_{prompt_dir.name}_{file_path.stem}"
        
        # 仮想環境があればsite-packagesをパスに追加
        self.dependency_manager.add_venv_to_path(prompt_dir.name)
        
        # モジュールを読み込む
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # 必須属性の確認
        if not hasattr(module, 'create_prompt'):
            raise ValueError(f"{file_path.name}に必須関数 'create_prompt' がありません")
        
        # プロンプトIDはファイル名をそのまま使用（互換性維持）
        # 例: normal_prompt.py → prompt_id = "normal_prompt"
        prompt_id = file_path.stem  # "_prompt" を除去しない
        
        # 仮想環境情報
        venv_python = self.dependency_manager.get_venv_python(prompt_dir.name)
        
        # 設定スキーマを取得（存在する場合）
        settings_schema = None
        if hasattr(module, 'get_settings_schema'):
            settings_schema = module.get_settings_schema()
            
            # デフォルト設定を初期化
            if prompt_id not in self.prompt_settings:
                self.prompt_settings[prompt_id] = {}
                if settings_schema:
                    for key, config in settings_schema.items():
                        self.prompt_settings[prompt_id][key] = config.get('default')
                self._save_settings()
        
        # プロンプト情報を保存
        self.loaded_prompts[prompt_id] = {
            "module": module,
            "name": getattr(module, 'PROMPT_NAME', prompt_id),
            "description": getattr(module, 'PROMPT_DESCRIPTION', ''),
            "create_prompt": module.create_prompt,
            "file_path": str(file_path),
            "prompt_dir": str(prompt_dir),
            "has_venv": venv_python is not None,
            "venv_python": venv_python,
            "settings_schema": settings_schema
        }
        
        venv_status = "（専用仮想環境使用）" if venv_python else ""
        print(f"  ✓ プロンプト読み込み成功: {self.loaded_prompts[prompt_id]['name']} ({prompt_id}) {venv_status}")
    
    def get_prompt(self, prompt_id: str, user_input: str = "", context: dict = None) -> str:
        """
        指定されたプロンプトを取得
        
        Args:
            prompt_id: プロンプトID（例: "normal_prompt"）
            user_input: ユーザー入力
            context: 実行コンテキスト
        
        Returns:
            生成されたプロンプト文字列
        """
        if prompt_id not in self.loaded_prompts:
            print(f"警告: プロンプト '{prompt_id}' が見つかりません。デフォルトを使用します。")
            return self._get_default_prompt(user_input)
        
        prompt_info = self.loaded_prompts[prompt_id]
        
        # コンテキストを準備
        enhanced_context = context or {}
        enhanced_context['prompt_dir'] = prompt_info['prompt_dir']
        enhanced_context['settings'] = self.prompt_settings.get(prompt_id, {})
        enhanced_context['has_venv'] = prompt_info['has_venv']
        enhanced_context['venv_python'] = prompt_info['venv_python']
        
        try:
            # create_prompt関数を呼び出し
            create_prompt_func = prompt_info['create_prompt']
            
            # 引数の数を確認（後方互換性のため）
            import inspect
            sig = inspect.signature(create_prompt_func)
            params = list(sig.parameters.keys())
            
            if len(params) >= 2:
                return create_prompt_func(user_input, enhanced_context)
            else:
                return create_prompt_func(user_input)
                
        except Exception as e:
            print(f"プロンプト生成エラー ({prompt_id}): {e}")
            return self._get_default_prompt(user_input)
    
    def _get_default_prompt(self, user_input: str) -> str:
        """デフォルトのプロンプトを返す"""
        from datetime import datetime
        now = datetime.now()
        time_str = now.strftime('%Y年%m月%d日 %H時%M分')
        
        return f"""あなたは親切で知識豊富なAIアシスタントです。
現在時刻: {time_str}

質問に対して正確で分かりやすい回答を心がけてください。
"""
    
    def get_system_prompt(self, prompt_id: str, context: dict = None) -> str:
        """
        システムプロンプト部分のみを取得（ユーザー入力なし）
        
        Args:
            prompt_id: プロンプトID
            context: 実行コンテキスト
        
        Returns:
            システムプロンプト文字列
        """
        return self.get_prompt(prompt_id, "", context)
    
    def get_available_prompts(self) -> List[Dict[str, str]]:
        """利用可能なプロンプトのリストを取得"""
        prompts = []
        for prompt_id, info in self.loaded_prompts.items():
            prompts.append({
                'id': prompt_id,
                'name': info['name'],
                'description': info.get('description', '')
            })
        
        # 'normal_prompt' を先頭に
        prompts.sort(key=lambda x: x['id'] != 'normal_prompt')
        return prompts
    
    def get_prompt_settings(self, prompt_id: str) -> dict:
        """特定のプロンプトの設定を取得"""
        return self.prompt_settings.get(prompt_id, {})
    
    def update_prompt_settings(self, prompt_id: str, settings: dict) -> bool:
        """プロンプトの設定を更新"""
        try:
            if prompt_id not in self.prompt_settings:
                self.prompt_settings[prompt_id] = {}
            self.prompt_settings[prompt_id].update(settings)
            self._save_settings()
            return True
        except Exception as e:
            print(f"設定更新エラー: {e}")
            return False
    
    def get_all_prompts_with_settings(self) -> dict:
        """すべてのプロンプトと設定スキーマを取得"""
        result = {}
        
        for prompt_id, prompt_info in self.loaded_prompts.items():
            result[prompt_id] = {
                "name": prompt_info["name"],
                "description": prompt_info["description"],
                "has_venv": prompt_info["has_venv"],
                "settings_schema": prompt_info.get("settings_schema"),
                "current_settings": self.prompt_settings.get(prompt_id, {}),
                "is_loaded": True
            }
        
        return result
    
    def reload_all_prompts(self) -> dict:
        """すべてのプロンプトを再読み込み"""
        print("\n=== プロンプトの再読み込みを開始 ===")
        
        # 既存のプロンプトをクリア
        self.loaded_prompts.clear()
        
        # モジュールキャッシュをクリア
        modules_to_remove = [m for m in sys.modules if m.startswith('prompt_')]
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # 再読み込み
        self.load_all_prompts()
        
        loaded_count = len(self.loaded_prompts)
        print(f"\n=== 再読み込み完了: {loaded_count}個のプロンプト ===")
        
        return {
            "success": True,
            "loaded_count": loaded_count,
            "prompts": self.get_available_prompts()
        }
