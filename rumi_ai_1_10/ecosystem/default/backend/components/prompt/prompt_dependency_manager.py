"""
プロンプト用の依存関係管理システム
各プロンプトフォルダの仮想環境と依存関係を管理する
"""

import os
import sys
import subprocess
import venv
import platform
from pathlib import Path
from typing import Optional


class PromptDependencyManager:
    """プロンプトの依存関係を管理するクラス"""
    
    def __init__(self, prompt_base_dir: Path):
        """
        初期化
        
        Args:
            prompt_base_dir: promptフォルダのパス
        """
        self.prompt_base_dir = prompt_base_dir
        self.venv_cache = {}  # プロンプト名 -> venv Pythonパス
    
    def get_venv_python(self, prompt_name: str) -> Optional[str]:
        """
        プロンプト専用の仮想環境のPythonパスを取得
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            Pythonパス、または仮想環境がない場合はNone
        """
        if prompt_name in self.venv_cache:
            return self.venv_cache[prompt_name]
        
        prompt_dir = self.prompt_base_dir / prompt_name
        venv_dir = prompt_dir / ".venv"
        
        if platform.system() == "Windows":
            python_path = venv_dir / "Scripts" / "python.exe"
        else:
            python_path = venv_dir / "bin" / "python"
        
        if python_path.exists():
            self.venv_cache[prompt_name] = str(python_path)
            return str(python_path)
        
        return None
    
    def create_venv(self, prompt_name: str) -> bool:
        """
        プロンプト専用の仮想環境を作成
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        prompt_dir = self.prompt_base_dir / prompt_name
        venv_dir = prompt_dir / ".venv"
        
        if venv_dir.exists():
            print(f"  仮想環境は既に存在します: {venv_dir}")
            return True
        
        try:
            print(f"  仮想環境を作成中: {venv_dir}")
            venv.create(venv_dir, with_pip=True)
            
            # pipをアップグレード
            venv_python = self.get_venv_python(prompt_name)
            if venv_python:
                subprocess.run(
                    [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            return True
        except Exception as e:
            print(f"  仮想環境の作成に失敗: {e}")
            return False
    
    def install_requirements(self, prompt_name: str) -> bool:
        """
        requirements.txtから依存関係をインストール
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        prompt_dir = self.prompt_base_dir / prompt_name
        requirements_file = prompt_dir / "requirements.txt"
        
        if not requirements_file.exists():
            return True  # requirements.txtがない場合は成功とみなす
        
        # 仮想環境のPythonパスを取得
        venv_python = self.get_venv_python(prompt_name)
        
        if not venv_python:
            # 仮想環境が存在しない場合は作成
            if not self.create_venv(prompt_name):
                return False
            venv_python = self.get_venv_python(prompt_name)
        
        print(f"  requirements.txt をインストール中...")
        
        # インストール状態を記録するファイル
        venv_dir = prompt_dir / ".venv"
        installed_marker = venv_dir / "requirements_installed.txt"
        
        # requirements.txtの内容をチェック
        with open(requirements_file, 'r', encoding='utf-8') as f:
            requirements_content = f.read()
        
        # 既にインストール済みかチェック
        if installed_marker.exists():
            with open(installed_marker, 'r', encoding='utf-8') as f:
                installed_content = f.read()
            if installed_content == requirements_content:
                print(f"  requirements.txt は既にインストール済みです")
                return True
        
        try:
            result = subprocess.run(
                [venv_python, "-m", "pip", "install", "-r", str(requirements_file)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"  ✓ requirements.txt のインストールが完了しました")
                with open(installed_marker, 'w', encoding='utf-8') as f:
                    f.write(requirements_content)
                return True
            else:
                print(f"  ✗ インストールエラー: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"  ✗ インストールがタイムアウトしました")
            return False
        except Exception as e:
            print(f"  ✗ インストール中にエラーが発生: {e}")
            return False
    
    def check_and_install(self, prompt_name: str) -> bool:
        """
        依存関係をチェックし、必要に応じてインストール
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        prompt_dir = self.prompt_base_dir / prompt_name
        requirements_file = prompt_dir / "requirements.txt"
        
        if not requirements_file.exists():
            return True  # 依存関係なし
        
        print(f"  プロンプト '{prompt_name}' の依存関係をチェック中...")
        
        # 仮想環境の作成
        if not self.create_venv(prompt_name):
            return False
        
        # 依存関係のインストール
        return self.install_requirements(prompt_name)
    
    def add_venv_to_path(self, prompt_name: str) -> bool:
        """
        仮想環境のsite-packagesをsys.pathに追加
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        prompt_dir = self.prompt_base_dir / prompt_name
        venv_dir = prompt_dir / ".venv"
        
        if not venv_dir.exists():
            return False
        
        if platform.system() == "Windows":
            site_packages = venv_dir / "Lib" / "site-packages"
        else:
            python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            site_packages = venv_dir / "lib" / python_version / "site-packages"
        
        if site_packages.exists() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
            return True
        
        return False
    
    def remove_venv(self, prompt_name: str) -> bool:
        """
        プロンプト専用の仮想環境を削除
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        import shutil
        
        prompt_dir = self.prompt_base_dir / prompt_name
        venv_dir = prompt_dir / ".venv"
        
        if not venv_dir.exists():
            print(f"  仮想環境が存在しません: {venv_dir}")
            return True
        
        try:
            print(f"  仮想環境を削除中: {venv_dir}")
            shutil.rmtree(venv_dir)
            
            # キャッシュからも削除
            if prompt_name in self.venv_cache:
                del self.venv_cache[prompt_name]
            
            print(f"  ✓ 仮想環境を削除しました")
            return True
        except Exception as e:
            print(f"  ✗ 仮想環境の削除に失敗: {e}")
            return False
    
    def get_installed_packages(self, prompt_name: str) -> list:
        """
        インストール済みパッケージのリストを取得
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            パッケージ情報のリスト
        """
        venv_python = self.get_venv_python(prompt_name)
        
        if not venv_python:
            return []
        
        try:
            result = subprocess.run(
                [venv_python, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            else:
                return []
        except Exception as e:
            print(f"  パッケージリストの取得に失敗: {e}")
            return []
    
    def get_venv_status(self, prompt_name: str) -> dict:
        """
        仮想環境のステータスを取得
        
        Args:
            prompt_name: プロンプト名（フォルダ名）
        
        Returns:
            ステータス情報の辞書
        """
        prompt_dir = self.prompt_base_dir / prompt_name
        venv_dir = prompt_dir / ".venv"
        requirements_file = prompt_dir / "requirements.txt"
        
        status = {
            "prompt_name": prompt_name,
            "has_requirements": requirements_file.exists(),
            "has_venv": venv_dir.exists(),
            "venv_python": self.get_venv_python(prompt_name),
            "packages": []
        }
        
        if status["has_venv"] and status["venv_python"]:
            status["packages"] = self.get_installed_packages(prompt_name)
        
        return status
