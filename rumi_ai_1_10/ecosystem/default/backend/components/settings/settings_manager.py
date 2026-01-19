# settings_manager.py
import os
import csv
import json
import importlib.util
import warnings
from pathlib import Path
from typing import Dict, List, Any, Optional


class SettingsManager:
    def __init__(self, user_data_dir: str = None):
        """
        Args:
            user_data_dir: ユーザーデータディレクトリ（setup.pyから注入される）
        """
        if user_data_dir is None:
            user_data_dir = 'user_data'
        
        self.user_data_dir = Path(user_data_dir)
        self.user_data_dir.mkdir(exist_ok=True)
        self.settings_file = self.user_data_dir / 'user.csv'
        self.prompt_dir = Path('prompt')  # 注: これは将来promptコンポーネントが管理
        self.default_budgets = {
            'pro': 32768,
            'flash': 24576,
            'lite': 24576
        }
        self._initialize_settings()
    
    def _initialize_settings(self):
        """設定ファイルを初期化"""
        if not self.settings_file.exists():
            with open(self.settings_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'user_id', 'theme', 'model', 'thinking_on', 
                    'thinking_budget_pro', 'thinking_budget_flash', 'thinking_budget_lite',
                    'streaming_on', 'favorite_models', 'debug_mode', 'max_iterations'
                ])
                writer.writerow([
                    'default_user', 'dark', 'gemini-2.5-flash', 'true',
                    self.default_budgets['pro'], self.default_budgets['flash'], 
                    self.default_budgets['lite'], 'false',
                    'gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite',
                    'false',
                    '15'
                ])
    
    def get_user_settings(self, user_id: str = 'default_user') -> Dict[str, Any]:
        """ユーザー設定を取得"""
        try:
            with open(self.settings_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row and row.get('user_id') == user_id:
                        row['model'] = row.get('model', 'gemini-2.5-flash')
                        row['thinking_on'] = row.get('thinking_on', 'true').lower() == 'true'
                        row['thinking_budget_pro'] = int(row.get('thinking_budget_pro', self.default_budgets['pro']))
                        row['thinking_budget_flash'] = int(row.get('thinking_budget_flash', self.default_budgets['flash']))
                        row['thinking_budget_lite'] = int(row.get('thinking_budget_lite', self.default_budgets['lite']))
                        row['streaming_on'] = row.get('streaming_on', 'false').lower() == 'true'
                        
                        # デバッグモード
                        row['debug_mode'] = row.get('debug_mode', 'false').lower() == 'true'
                        
                        # max_iterations
                        row['max_iterations'] = int(row.get('max_iterations', '15'))
                        
                        # お気に入りモデルをリストに変換
                        favorite_models_str = row.get('favorite_models', '')
                        row['favorite_models'] = [m.strip() for m in favorite_models_str.split(',') if m.strip()]
                        
                        return row
        except Exception as e:
            print(f"設定ファイルの読み込みエラー: {e}")
        
        return {
            'user_id': user_id,
            'theme': 'dark',
            'model': 'gemini-2.5-flash',
            'thinking_on': True,
            'thinking_budget_pro': self.default_budgets['pro'],
            'thinking_budget_flash': self.default_budgets['flash'],
            'thinking_budget_lite': self.default_budgets['lite'],
            'streaming_on': False,
            'favorite_models': ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite'],
            'debug_mode': False,
            'max_iterations': 15
        }
    
    def save_user_settings(self, settings: Dict[str, Any], user_id: str = 'default_user'):
        """ユーザー設定を保存"""
        rows, user_found = [], False
        fieldnames = [
            'user_id', 'theme', 'model', 'thinking_on',
            'thinking_budget_pro', 'thinking_budget_flash', 'thinking_budget_lite',
            'streaming_on', 'favorite_models', 'debug_mode', 'max_iterations'
        ]
        
        try:
            with open(self.settings_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, [])
                if set(header) != set(fieldnames):
                    rows.append(fieldnames)
                    for old_row in reader:
                        new_row_dict = dict(zip(header, old_row))
                        # favorite_modelsがない場合はデフォルト値を設定
                        if 'favorite_models' not in new_row_dict:
                            new_row_dict['favorite_models'] = 'gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite'
                        # debug_modeがない場合はデフォルト値を設定
                        if 'debug_mode' not in new_row_dict:
                            new_row_dict['debug_mode'] = 'false'
                        # max_iterationsがない場合はデフォルト値を設定
                        if 'max_iterations' not in new_row_dict:
                            new_row_dict['max_iterations'] = '15'
                        rows.append([new_row_dict.get(fn, '') for fn in fieldnames])
                else:
                    rows.extend([header] + list(reader))
        except (IOError, FileNotFoundError):
            rows.append(fieldnames)
        
        final_rows = [rows[0]] if rows else [fieldnames]
        
        for row_list in rows[1:]:
            row = dict(zip(rows[0], row_list))
            if not row:
                continue
            if row.get('user_id') == user_id:
                user_found = True
                
                # favorite_modelsをカンマ区切り文字列に変換
                favorite_models = settings.get('favorite_models', row.get('favorite_models', []))
                if isinstance(favorite_models, list):
                    favorite_models_str = ','.join(favorite_models)
                else:
                    favorite_models_str = favorite_models
                
                updated_row = {
                    'user_id': user_id,
                    'theme': settings.get('theme', row.get('theme')),
                    'model': settings.get('model', row.get('model')),
                    'thinking_on': str(settings.get('thinking_on', row.get('thinking_on'))).lower(),
                    'thinking_budget_pro': settings.get('thinking_budget_pro', row.get('thinking_budget_pro')),
                    'thinking_budget_flash': settings.get('thinking_budget_flash', row.get('thinking_budget_flash')),
                    'thinking_budget_lite': settings.get('thinking_budget_lite', row.get('thinking_budget_lite')),
                    'streaming_on': str(settings.get('streaming_on', row.get('streaming_on', False))).lower(),
                    'favorite_models': favorite_models_str,
                    'debug_mode': str(settings.get('debug_mode', row.get('debug_mode', False))).lower(),
                    'max_iterations': settings.get('max_iterations', row.get('max_iterations', 15))
                }
                final_rows.append([updated_row.get(fn) for fn in fieldnames])
            else:
                final_rows.append(row_list)
        
        if not user_found:
            default_settings = self.get_user_settings(user_id)
            default_settings.update(settings)
            
            # favorite_modelsを文字列に変換
            favorite_models = default_settings.get('favorite_models', [])
            if isinstance(favorite_models, list):
                favorite_models_str = ','.join(favorite_models)
            else:
                favorite_models_str = favorite_models
            default_settings['favorite_models'] = favorite_models_str
            
            final_rows.append([
                str(default_settings.get(fn, '')).lower() if isinstance(default_settings.get(fn), bool) 
                else default_settings.get(fn, '') 
                for fn in fieldnames
            ])
        
        with open(self.settings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(final_rows)
    
    def get_available_prompts(self) -> List[Dict[str, str]]:
        """
        利用可能なプロンプトのリストを取得
        
        非推奨: PromptLoader.get_available_prompts() を使用してください
        """
        warnings.warn(
            "SettingsManager.get_available_prompts() は非推奨です。"
            "PromptLoader.get_available_prompts() を使用してください。",
            DeprecationWarning,
            stacklevel=2
        )
        
        prompts = []
        
        # プロンプトディレクトリが存在しない場合は空リストを返す
        if not self.prompt_dir.exists():
            return prompts
        
        # 新構造: prompt/[name]/[name]_prompt.py
        for item in self.prompt_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                if item.name == 'userdata':
                    continue
                for file_path in item.glob('*_prompt.py'):
                    module_name = file_path.stem
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        if hasattr(module, 'create_prompt'):
                            prompt_name = getattr(module, 'PROMPT_NAME', module_name)
                            prompts.append({
                                'id': module_name,
                                'name': prompt_name
                            })
                    except Exception as e:
                        print(f"プロンプト読み込みエラー ({module_name}): {e}")
        
        # 旧構造との互換性: prompt/*.py（フォルダ外の直接配置）
        for file_path in self.prompt_dir.glob('*_prompt.py'):
            if file_path.is_file():
                module_name = file_path.stem
                # 既に読み込み済みかチェック
                if any(p['id'] == module_name for p in prompts):
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'create_prompt'):
                        prompt_name = getattr(module, 'PROMPT_NAME', module_name)
                        prompts.append({
                            'id': module_name,
                            'name': prompt_name
                        })
                except Exception as e:
                    print(f"プロンプト読み込みエラー ({module_name}): {e}")
        
        # normal_promptを先頭に
        prompts.sort(key=lambda x: x['id'] != 'normal_prompt')
        return prompts
