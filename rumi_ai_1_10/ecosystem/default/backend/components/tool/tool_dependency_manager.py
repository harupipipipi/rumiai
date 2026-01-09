"""
ツール用の依存関係管理システム
各ツールフォルダの仮想環境と依存関係を管理する
"""

import os
import sys
import subprocess
import venv
import platform
from pathlib import Path
from typing import Optional


class ToolDependencyManager:
    """ツールの依存関係を管理するクラス"""
    
    def __init__(self, tool_base_dir: Path):
        """
        初期化
        
        Args:
            tool_base_dir: toolフォルダのパス
        """
        self.tool_base_dir = tool_base_dir
        self.venv_cache = {}  # ツール名 -> venv Pythonパス
        
        # プロジェクトの仮想環境のPython
        self.main_venv_python = self._find_main_venv_python()
    
    def _find_main_venv_python(self) -> str:
        """メインプロジェクトの仮想環境のPythonを見つける"""
        project_root = self.tool_base_dir.parent
        
        venv_python_win = project_root / ".venv" / "Scripts" / "python.exe"
        venv_python_unix = project_root / ".venv" / "bin" / "python"
        
        if venv_python_win.exists():
            return str(venv_python_win)
        elif venv_python_unix.exists():
            return str(venv_python_unix)
        else:
            return sys.executable
    
    def get_venv_python(self, tool_name: str) -> Optional[str]:
        """
        ツール専用の仮想環境のPythonパスを取得
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            Pythonパス、または仮想環境がない場合はNone
        """
        if tool_name in self.venv_cache:
            return self.venv_cache[tool_name]
        
        tool_dir = self.tool_base_dir / tool_name
        venv_dir = tool_dir / ".venv"
        
        if platform.system() == "Windows":
            python_path = venv_dir / "Scripts" / "python.exe"
        else:
            python_path = venv_dir / "bin" / "python"
        
        if python_path.exists():
            self.venv_cache[tool_name] = str(python_path)
            return str(python_path)
        
        return None
    
    def create_venv(self, tool_name: str) -> bool:
        """
        ツール専用の仮想環境を作成
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        tool_dir = self.tool_base_dir / tool_name
        venv_dir = tool_dir / ".venv"
        
        if venv_dir.exists():
            print(f"  仮想環境は既に存在します: {venv_dir}")
            return True
        
        try:
            print(f"  仮想環境を作成中: {venv_dir}")
            venv.create(venv_dir, with_pip=True)
            
            venv_python = self.get_venv_python(tool_name)
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
    
    def install_requirements(self, tool_name: str) -> bool:
        """
        requirements.txtから依存関係をインストール
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        tool_dir = self.tool_base_dir / tool_name
        requirements_file = tool_dir / "requirements.txt"
        
        if not requirements_file.exists():
            return True  # requirements.txtがない場合は成功とみなす
        
        venv_python = self.get_venv_python(tool_name)
        
        if not venv_python:
            if not self.create_venv(tool_name):
                return False
            venv_python = self.get_venv_python(tool_name)
        
        print(f"  requirements.txt をインストール中...")
        
        venv_dir = tool_dir / ".venv"
        installed_marker = venv_dir / "requirements_installed.txt"
        
        with open(requirements_file, 'r', encoding='utf-8') as f:
            requirements_content = f.read()
        
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
    
    def check_and_install(self, tool_name: str) -> bool:
        """
        依存関係をチェックし、必要に応じてインストール
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        tool_dir = self.tool_base_dir / tool_name
        requirements_file = tool_dir / "requirements.txt"
        
        if not requirements_file.exists():
            return True  # 依存関係なし
        
        print(f"  ツール '{tool_name}' の依存関係をチェック中...")
        
        if not self.create_venv(tool_name):
            return False
        
        return self.install_requirements(tool_name)
    
    def add_venv_to_path(self, tool_name: str) -> bool:
        """
        仮想環境のsite-packagesをsys.pathに追加
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        tool_dir = self.tool_base_dir / tool_name
        venv_dir = tool_dir / ".venv"
        
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
    
    def remove_venv_from_path(self, tool_name: str) -> bool:
        """
        仮想環境のsite-packagesをsys.pathから削除
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        tool_dir = self.tool_base_dir / tool_name
        venv_dir = tool_dir / ".venv"
        
        if platform.system() == "Windows":
            site_packages = venv_dir / "Lib" / "site-packages"
        else:
            python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            site_packages = venv_dir / "lib" / python_version / "site-packages"
        
        site_packages_str = str(site_packages)
        if site_packages_str in sys.path:
            sys.path.remove(site_packages_str)
            return True
        
        return False
    
    def get_installed_packages(self, tool_name: str) -> list:
        """
        ツールの仮想環境にインストールされているパッケージ一覧を取得
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            パッケージ情報のリスト
        """
        venv_python = self.get_venv_python(tool_name)
        
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
            print(f"パッケージ一覧の取得に失敗: {e}")
            return []
    
    def clear_venv_cache(self):
        """仮想環境パスのキャッシュをクリア"""
        self.venv_cache.clear()
    
    def delete_venv(self, tool_name: str) -> bool:
        """
        ツールの仮想環境を削除
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        import shutil
        
        tool_dir = self.tool_base_dir / tool_name
        venv_dir = tool_dir / ".venv"
        
        if not venv_dir.exists():
            return True
        
        # パスから削除
        self.remove_venv_from_path(tool_name)
        
        # キャッシュから削除
        if tool_name in self.venv_cache:
            del self.venv_cache[tool_name]
        
        try:
            shutil.rmtree(venv_dir)
            print(f"  仮想環境を削除しました: {venv_dir}")
            return True
        except Exception as e:
            print(f"  仮想環境の削除に失敗: {e}")
            return False
    
    def rebuild_venv(self, tool_name: str) -> bool:
        """
        ツールの仮想環境を再構築
        
        Args:
            tool_name: ツール名（フォルダ名）
        
        Returns:
            成功した場合True
        """
        print(f"  ツール '{tool_name}' の仮想環境を再構築中...")
        
        # 既存の仮想環境を削除
        if not self.delete_venv(tool_name):
            return False
        
        # 新しい仮想環境を作成してインストール
        return self.check_and_install(tool_name)
