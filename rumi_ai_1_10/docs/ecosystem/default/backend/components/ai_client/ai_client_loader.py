# ecosystem/default/backend/components/ai_client/ai_client_loader.py
"""
AIクライアントの動的読み込みシステム
ai_client/配下の各プロバイダーディレクトリを自動検出し、
クライアントとプロファイルを読み込む
"""

import os
import json
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


class AIClientLoader:
    """AIクライアントを動的に読み込むローダー"""
    
    def __init__(self, ai_client_dir: Path = None):
        """ローダーを初期化"""
        if ai_client_dir is None:
            # エコシステム経由でパス解決を試みる
            try:
                from backend_core.ecosystem.compat import get_ai_clients_assets_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    ai_client_dir = get_ai_clients_assets_dir()
                else:
                    ai_client_dir = Path(__file__).parent
            except ImportError:
                ai_client_dir = Path(__file__).parent
        
        self.ai_client_dir = Path(ai_client_dir)
        self.loaded_clients = {}
        self.model_profiles = {}
        self.provider_model_map = {}
        
        # 依存関係マネージャーを動的にインポート・初期化
        self.dependency_manager = self._load_dependency_manager()
    
    def _load_dependency_manager(self):
        """DependencyManagerを動的に読み込む"""
        # dependency_manager は runtime側（ローダーファイルと同じ場所）にある
        # self.ai_client_dir は assets_dir を指す可能性があるため、
        # Path(__file__).parent を使用して runtime_dir を探す
        runtime_dir = Path(__file__).parent
        
        # ai_client_dependency_manager.py を探す
        dependency_manager_path = runtime_dir / "ai_client_dependency_manager.py"
        
        # フォールバック: 旧ファイル名も確認
        if not dependency_manager_path.exists():
            dependency_manager_path = runtime_dir / "dependency_manager.py"
        
        if not dependency_manager_path.exists():
            print(f"警告: dependency_manager が見つかりません: {runtime_dir}")
            return None
        
        try:
            spec = importlib.util.spec_from_file_location(
                "ai_client_dependency_manager", 
                dependency_manager_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules["ai_client_dependency_manager"] = module
            spec.loader.exec_module(module)
            
            # DependencyManagerクラスを取得してインスタンス化
            # 注意: DependencyManager には assets_dir を渡す
            if hasattr(module, 'DependencyManager'):
                return module.DependencyManager(self.ai_client_dir)
            else:
                print("警告: DependencyManagerクラスが見つかりません")
                return None
                
        except Exception as e:
            print(f"警告: DependencyManagerの読み込みに失敗: {e}")
            return None
    
    def load_all_clients(self):
        """ai_client/配下のすべてのクライアントを読み込む"""
        print("\n=== AI Client Loader: クライアントの読み込みを開始 ===")
        
        # ai_client/配下のディレクトリを探索
        for item in self.ai_client_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                # プロバイダーディレクトリを発見
                provider_name = item.name
                print(f"\nプロバイダーディレクトリを検出: {provider_name}")
                
                # クライアントファイルを探す
                client_file = item / f"{provider_name}_client.py"
                if client_file.exists():
                    self._load_client(provider_name, client_file, item)
                else:
                    print(f"  警告: クライアントファイルが見つかりません: {client_file}")
        
        print(f"\n=== 読み込み完了: {len(self.loaded_clients)}個のプロバイダー ===")
        self._print_summary()
    
    def _load_client(self, provider_name: str, client_file: Path, provider_dir: Path):
        """個別のクライアントを読み込む"""
        try:
            # 依存関係をチェック・インストール（dependency_managerがある場合のみ）
            if self.dependency_manager is not None:
                if not self.dependency_manager.check_and_install(provider_name, client_file):
                    print(f"  警告: {provider_name} の依存関係インストールに失敗しました。スキップします。")
                    return
                
                # 仮想環境のsite-packagesをパスに追加
                self.dependency_manager.add_venv_to_path(provider_name)
            
            # モジュール名を生成
            module_name = f"ai_client.{provider_name}.{provider_name}_client"
            
            # モジュールをインポート
            spec = importlib.util.spec_from_file_location(module_name, client_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # クライアントクラスを探す（大文字小文字を考慮）
            client_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr_name.lower() == f"{provider_name}client":
                    client_class = attr
                    break
            
            if not client_class:
                print(f"  エラー: {provider_name}Client クラスが見つかりません")
                return
            
            # 必須メソッドの確認
            required_methods = ['get_provider_name', 'get_profile_dir', 'send_request']
            for method in required_methods:
                if not hasattr(client_class, method):
                    print(f"  警告: 必須メソッド {method} が実装されていません")
            
            # プロファイルを読み込む
            profiles = self._load_profiles(client_class, provider_dir)
            
            if profiles:
                # クライアント情報を保存
                self.loaded_clients[provider_name] = {
                    'class': client_class,
                    'module': module,
                    'file': str(client_file),
                    'profiles': profiles
                }
                
                # モデルプロファイルを統合
                for model_id, profile in profiles.items():
                    # プロバイダー名を追加
                    profile['provider_name'] = provider_name
                    self.model_profiles[model_id] = profile
                
                # プロバイダー -> モデルIDマップを更新
                self.provider_model_map[provider_name] = list(profiles.keys())
                
                print(f"  ✓ クライアント読み込み成功: {len(profiles)}個のモデル")
            else:
                print(f"  警告: プロファイルが見つかりません")
                
        except Exception as e:
            print(f"  エラー: クライアント読み込み失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_profiles(self, client_class, provider_dir: Path) -> Dict[str, Dict]:
        """プロファイルディレクトリからJSONファイルを読み込む"""
        profiles = {}
        
        # プロファイルディレクトリを取得
        if hasattr(client_class, 'get_profile_dir'):
            profile_dir = client_class.get_profile_dir()
        else:
            profile_dir = provider_dir / "ai_profile"
        
        if not profile_dir.exists():
            print(f"  プロファイルディレクトリが存在しません: {profile_dir}")
            return profiles
        
        # JSONファイルを読み込む
        for json_file in profile_dir.glob("*.json"):
            if json_file.name.startswith('_'):
                continue  # アンダースコアで始まるファイルはスキップ
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                
                # 必須フィールドの検証
                if not self._validate_profile(profile, json_file.name):
                    continue
                
                model_id = profile['basic_info']['id']
                
                # ファイル名とIDの一致を確認
                if model_id != json_file.stem:
                    print(f"    警告: ファイル名 '{json_file.name}' とID '{model_id}' が一致しません")
                
                profiles[model_id] = profile
                print(f"    • {model_id}: {profile['basic_info']['name']}")
                
            except json.JSONDecodeError as e:
                print(f"    JSONエラー ({json_file.name}): {e}")
            except Exception as e:
                print(f"    読み込みエラー ({json_file.name}): {e}")
        
        return profiles
    
    def _validate_profile(self, profile: Dict, filename: str) -> bool:
        """プロファイルの必須フィールドを検証"""
        required_sections = ['basic_info', 'capabilities', 'features']
        
        for section in required_sections:
            if section not in profile:
                print(f"    エラー ({filename}): 必須セクション '{section}' が存在しません")
                return False
        
        # basic_info の必須フィールド
        basic_required = ['id', 'name', 'description', 'provider']
        for field in basic_required:
            if field not in profile['basic_info']:
                print(f"    エラー ({filename}): 必須フィールド 'basic_info.{field}' が存在しません")
                return False
        
        # capabilities の必須フィールド
        cap_required = ['context_length', 'max_completion_tokens', 'supported_parameters']
        for field in cap_required:
            if field not in profile['capabilities']:
                print(f"    エラー ({filename}): 必須フィールド 'capabilities.{field}' が存在しません")
                return False
        
        # features の必須フィールド
        feat_required = ['supports_function_calling', 'supports_streaming', 'is_multimodal', 
                        'input_modalities', 'output_modalities', 'supports_reasoning']
        for field in feat_required:
            if field not in profile['features']:
                print(f"    エラー ({filename}): 必須フィールド 'features.{field}' が存在しません")
                return False
        
        return True
    
    def get_client(self, provider_name: str, api_key: str = None):
        """
        指定されたプロバイダーのクライアントインスタンスを取得
        
        Args:
            provider_name: プロバイダー名
            api_key: APIキー（互換性のため残すが使用しない）
        
        Returns:
            クライアントインスタンス
        """
        if provider_name not in self.loaded_clients:
            print(f"プロバイダー {provider_name} が見つかりません")
            return None
        
        client_info = self.loaded_clients[provider_name]
        
        # クライアントインスタンスを作成（APIキーは各クライアントが自分で取得）
        try:
            client_instance = client_info['class']()  # 引数なしで初期化
            print(f"クライアントインスタンスを作成: {provider_name}")
            return client_instance
        except Exception as e:
            print(f"クライアントの初期化に失敗: {provider_name}")
            print(f"エラー: {e}")
            return None
    
    def get_model_profile(self, model_id: str) -> Optional[Dict]:
        """
        指定されたモデルIDのプロファイルを取得
        
        Args:
            model_id: モデルID
        
        Returns:
            モデルプロファイル
        """
        return self.model_profiles.get(model_id)
    
    def get_all_models(self) -> List[Dict]:
        """
        すべてのモデル情報をリスト形式で取得
        
        Returns:
            モデル情報のリスト
        """
        models = []
        for model_id, profile in self.model_profiles.items():
            models.append({
                'id': model_id,
                'name': profile['basic_info']['name'],
                'description': profile['basic_info']['description'],
                'provider': profile['provider_name'],
                'features': profile.get('features', {}),
                'capabilities': profile.get('capabilities', {})
            })
        return models
    
    def search_models(self, **criteria) -> List[Dict]:
        """
        条件に基づいてモデルを検索
        
        Args:
            **criteria: 検索条件（例: is_multimodal=True, supports_function_calling=True）
        
        Returns:
            条件に一致するモデルのリスト
        """
        matching_models = []
        
        for model_id, profile in self.model_profiles.items():
            match = True
            
            # 各条件をチェック
            for key, value in criteria.items():
                if key == 'provider':
                    if profile['provider_name'] != value:
                        match = False
                        break
                elif key == 'is_multimodal':
                    if profile.get('features', {}).get('is_multimodal') != value:
                        match = False
                        break
                elif key == 'supports_function_calling':
                    if profile.get('features', {}).get('supports_function_calling') != value:
                        match = False
                        break
                elif key == 'supports_streaming':
                    if profile.get('features', {}).get('supports_streaming') != value:
                        match = False
                        break
                elif key == 'supports_reasoning':
                    if profile.get('features', {}).get('supports_reasoning') != value:
                        match = False
                        break
                elif key == 'min_context_length':
                    if profile.get('capabilities', {}).get('context_length', 0) < value:
                        match = False
                        break
            
            if match:
                matching_models.append({
                    'id': model_id,
                    'name': profile['basic_info']['name'],
                    'description': profile['basic_info']['description'],
                    'provider': profile['provider_name'],
                    'features': profile.get('features', {}),
                    'capabilities': profile.get('capabilities', {})
                })
        
        return matching_models
    
    def get_provider_models(self, provider_name: str) -> List[str]:
        """
        指定されたプロバイダーのモデルIDリストを取得
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            モデルIDのリスト
        """
        return self.provider_model_map.get(provider_name, [])
    
    def _print_summary(self):
        """読み込み結果のサマリーを表示"""
        print("\n=== 読み込みサマリー ===")
        print(f"プロバイダー数: {len(self.loaded_clients)}")
        print(f"総モデル数: {len(self.model_profiles)}")
        
        if self.loaded_clients:
            print("\nプロバイダー別モデル数:")
            for provider, model_ids in self.provider_model_map.items():
                print(f"  • {provider}: {len(model_ids)}モデル")
        
        # 機能別の統計
        multimodal_count = sum(1 for p in self.model_profiles.values() 
                              if p.get('features', {}).get('is_multimodal'))
        fc_count = sum(1 for p in self.model_profiles.values() 
                      if p.get('features', {}).get('supports_function_calling'))
        streaming_count = sum(1 for p in self.model_profiles.values() 
                             if p.get('features', {}).get('supports_streaming'))
        reasoning_count = sum(1 for p in self.model_profiles.values() 
                             if p.get('features', {}).get('supports_reasoning'))
        
        print("\n機能別モデル数:")
        print(f"  • マルチモーダル対応: {multimodal_count}")
        print(f"  • Function Calling対応: {fc_count}")
        print(f"  • ストリーミング対応: {streaming_count}")
        print(f"  • 推論機能対応: {reasoning_count}")
    
    def reload_all(self):
        """すべてのクライアントとプロファイルを再読み込み"""
        print("\n=== クライアントの再読み込みを開始 ===")
        
        # 既存のデータをクリア
        self.loaded_clients.clear()
        self.model_profiles.clear()
        self.provider_model_map.clear()
        
        # モジュールキャッシュをクリア
        modules_to_remove = []
        for module_name in sys.modules:
            if module_name.startswith('ai_client.'):
                modules_to_remove.append(module_name)
        
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # 再読み込み
        self.load_all_clients()
