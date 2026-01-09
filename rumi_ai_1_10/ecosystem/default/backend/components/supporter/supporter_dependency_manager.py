# supporter/supporter_dependency_manager.py
"""
サポーターの依存関係（仮想環境）を管理するモジュール
"""

import os
import sys
import subprocess
import venv
from pathlib import Path
from typing import Optional, Dict, Any, List


class SupporterDependencyManager:
    """
    サポーターごとの仮想環境と依存関係を管理するクラス
    """
    
    def __init__(self, supporter_dir: str = 'supporter'):
        """
        SupporterDependencyManagerを初期化
        
        Args:
            supporter_dir: サポーターディレクトリのパス
        """
        self.supporter_dir = Path(supporter_dir)
    
    def get_venv_path(self, supporter_name: str) -> Path:
        """サポーターの仮想環境パスを取得"""
        return self.supporter_dir / supporter_name / '.venv'
    
    def get_requirements_path(self, supporter_name: str) -> Path:
        """サポーターのrequirements.txtパスを取得"""
        return self.supporter_dir / supporter_name / 'requirements.txt'
    
    def has_requirements(self, supporter_name: str) -> bool:
        """requirements.txtが存在するかチェック"""
        return self.get_requirements_path(supporter_name).exists()
    
    def has_venv(self, supporter_name: str) -> bool:
        """仮想環境が存在するかチェック"""
        venv_path = self.get_venv_path(supporter_name)
        if not venv_path.exists():
            return False
        
        # Python実行ファイルの存在確認
        if sys.platform == 'win32':
            python_path = venv_path / 'Scripts' / 'python.exe'
        else:
            python_path = venv_path / 'bin' / 'python'
        
        return python_path.exists()
    
    def get_venv_python(self, supporter_name: str) -> Optional[str]:
        """仮想環境のPythonパスを取得"""
        venv_path = self.get_venv_path(supporter_name)
        
        if sys.platform == 'win32':
            python_path = venv_path / 'Scripts' / 'python.exe'
        else:
            python_path = venv_path / 'bin' / 'python'
        
        if python_path.exists():
            return str(python_path)
        return None
    
    def create_venv(self, supporter_name: str) -> bool:
        """
        サポーター用の仮想環境を作成
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            作成成功の可否
        """
        venv_path = self.get_venv_path(supporter_name)
        
        try:
            print(f"仮想環境を作成中: {venv_path}")
            venv.create(venv_path, with_pip=True)
            print(f"仮想環境の作成完了: {supporter_name}")
            return True
        except Exception as e:
            print(f"仮想環境の作成に失敗 ({supporter_name}): {e}")
            return False
    
    def install_requirements(self, supporter_name: str) -> Dict[str, Any]:
        """
        requirements.txtから依存関係をインストール
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            インストール結果
        """
        requirements_path = self.get_requirements_path(supporter_name)
        
        if not requirements_path.exists():
            return {
                'success': False,
                'error': 'requirements.txt not found'
            }
        
        # 仮想環境がなければ作成
        if not self.has_venv(supporter_name):
            if not self.create_venv(supporter_name):
                return {
                    'success': False,
                    'error': 'Failed to create virtual environment'
                }
        
        python_path = self.get_venv_python(supporter_name)
        if not python_path:
            return {
                'success': False,
                'error': 'Python not found in virtual environment'
            }
        
        try:
            print(f"依存関係をインストール中: {supporter_name}")
            result = subprocess.run(
                [python_path, '-m', 'pip', 'install', '-r', str(requirements_path)],
                capture_output=True,
                text=True,
                timeout=300  # 5分タイムアウト
            )
            
            if result.returncode == 0:
                print(f"依存関係のインストール完了: {supporter_name}")
                return {
                    'success': True,
                    'output': result.stdout
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Installation timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_installed_packages(self, supporter_name: str) -> List[Dict[str, str]]:
        """
        インストール済みパッケージ一覧を取得
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            パッケージ情報のリスト
        """
        python_path = self.get_venv_python(supporter_name)
        if not python_path:
            return []
        
        try:
            result = subprocess.run(
                [python_path, '-m', 'pip', 'list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return []
            
        except Exception:
            return []
    
    def delete_venv(self, supporter_name: str) -> bool:
        """
        仮想環境を削除
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            削除成功の可否
        """
        venv_path = self.get_venv_path(supporter_name)
        
        if not venv_path.exists():
            return True
        
        try:
            import shutil
            shutil.rmtree(venv_path)
            print(f"仮想環境を削除: {supporter_name}")
            return True
        except Exception as e:
            print(f"仮想環境の削除に失敗 ({supporter_name}): {e}")
            return False
    
    def get_venv_status(self, supporter_name: str) -> Dict[str, Any]:
        """
        仮想環境のステータスを取得
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            ステータス情報
        """
        return {
            'has_requirements': self.has_requirements(supporter_name),
            'has_venv': self.has_venv(supporter_name),
            'venv_python': self.get_venv_python(supporter_name),
            'packages': self.get_installed_packages(supporter_name) if self.has_venv(supporter_name) else []
        }
    
    def ensure_dependencies(self, supporter_name: str) -> Dict[str, Any]:
        """
        依存関係が満たされていることを確認し、必要に応じてインストール
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            結果情報
        """
        if not self.has_requirements(supporter_name):
            return {
                'success': True,
                'message': 'No requirements.txt found, skipping'
            }
        
        if self.has_venv(supporter_name):
            return {
                'success': True,
                'message': 'Virtual environment already exists'
            }
        
        return self.install_requirements(supporter_name)
    
    def rebuild_venv(self, supporter_name: str) -> Dict[str, Any]:
        """
        仮想環境を再構築（削除して再作成）
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            結果情報
        """
        # 既存の仮想環境を削除
        if self.has_venv(supporter_name):
            if not self.delete_venv(supporter_name):
                return {
                    'success': False,
                    'error': 'Failed to delete existing virtual environment'
                }
        
        # 再インストール
        return self.install_requirements(supporter_name)
    
    def get_all_supporters_venv_status(self) -> Dict[str, Dict[str, Any]]:
        """
        全サポーターの仮想環境ステータスを取得
        
        Returns:
            サポーター名をキーとしたステータス情報の辞書
        """
        result = {}
        
        if not self.supporter_dir.exists():
            return result
        
        for item in self.supporter_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                manifest_file = item / 'manifest.json'
                if manifest_file.exists():
                    result[item.name] = self.get_venv_status(item.name)
        
        return result
    
    def install_package(self, supporter_name: str, package_name: str) -> Dict[str, Any]:
        """
        特定のパッケージをインストール
        
        Args:
            supporter_name: サポーター名
            package_name: パッケージ名
        
        Returns:
            インストール結果
        """
        # 仮想環境がなければ作成
        if not self.has_venv(supporter_name):
            if not self.create_venv(supporter_name):
                return {
                    'success': False,
                    'error': 'Failed to create virtual environment'
                }
        
        python_path = self.get_venv_python(supporter_name)
        if not python_path:
            return {
                'success': False,
                'error': 'Python not found in virtual environment'
            }
        
        try:
            print(f"パッケージをインストール中: {package_name} ({supporter_name})")
            result = subprocess.run(
                [python_path, '-m', 'pip', 'install', package_name],
                capture_output=True,
                text=True,
                timeout=120  # 2分タイムアウト
            )
            
            if result.returncode == 0:
                print(f"パッケージのインストール完了: {package_name}")
                return {
                    'success': True,
                    'output': result.stdout
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Installation timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def uninstall_package(self, supporter_name: str, package_name: str) -> Dict[str, Any]:
        """
        特定のパッケージをアンインストール
        
        Args:
            supporter_name: サポーター名
            package_name: パッケージ名
        
        Returns:
            アンインストール結果
        """
        python_path = self.get_venv_python(supporter_name)
        if not python_path:
            return {
                'success': False,
                'error': 'Virtual environment not found'
            }
        
        try:
            print(f"パッケージをアンインストール中: {package_name} ({supporter_name})")
            result = subprocess.run(
                [python_path, '-m', 'pip', 'uninstall', '-y', package_name],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"パッケージのアンインストール完了: {package_name}")
                return {
                    'success': True,
                    'output': result.stdout
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Uninstallation timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def upgrade_pip(self, supporter_name: str) -> Dict[str, Any]:
        """
        仮想環境のpipをアップグレード
        
        Args:
            supporter_name: サポーター名
        
        Returns:
            アップグレード結果
        """
        python_path = self.get_venv_python(supporter_name)
        if not python_path:
            return {
                'success': False,
                'error': 'Virtual environment not found'
            }
        
        try:
            result = subprocess.run(
                [python_path, '-m', 'pip', 'install', '--upgrade', 'pip'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'output': result.stdout
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
