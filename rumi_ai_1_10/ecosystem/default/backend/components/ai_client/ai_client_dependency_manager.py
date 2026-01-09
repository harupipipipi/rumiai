"""
AIクライアントの依存関係を管理するモジュール
Windows/Mac両対応
"""

import subprocess
import sys
import venv
import platform
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class DependencyManager:
    """各AIクライアントの依存関係を管理"""
    
    def __init__(self, ai_client_dir: Path):
        """
        DependencyManagerを初期化
        
        Args:
            ai_client_dir: ai_clientディレクトリのパス
        """
        self.ai_client_dir = ai_client_dir
        self.is_windows = platform.system() == "Windows"
        self.cache_filename = ".installed_packages.json"
    
    def get_venv_dir(self, provider_name: str) -> Path:
        """
        プロバイダー別の仮想環境ディレクトリを取得
        
        Args:
            provider_name: プロバイダー名（例: "gemini", "openai"）
        
        Returns:
            仮想環境ディレクトリのパス
        """
        return self.ai_client_dir / provider_name / ".venv"
    
    def get_python_executable(self, provider_name: str) -> Path:
        """
        仮想環境のPython実行ファイルパスを取得
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            Python実行ファイルのパス
        """
        venv_dir = self.get_venv_dir(provider_name)
        if self.is_windows:
            return venv_dir / "Scripts" / "python.exe"
        else:
            return venv_dir / "bin" / "python"
    
    def get_pip_executable(self, provider_name: str) -> Path:
        """
        仮想環境のpip実行ファイルパスを取得
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            pip実行ファイルのパス
        """
        venv_dir = self.get_venv_dir(provider_name)
        if self.is_windows:
            return venv_dir / "Scripts" / "pip.exe"
        else:
            return venv_dir / "bin" / "pip"
    
    def get_cache_file(self, provider_name: str) -> Path:
        """
        キャッシュファイルのパスを取得
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            キャッシュファイルのパス
        """
        return self.ai_client_dir / provider_name / self.cache_filename
    
    def ensure_venv(self, provider_name: str) -> bool:
        """
        仮想環境が存在しなければ作成
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            成功した場合True
        """
        venv_dir = self.get_venv_dir(provider_name)
        
        # 既存の仮想環境をチェック
        if venv_dir.exists():
            python_exe = self.get_python_executable(provider_name)
            if python_exe.exists():
                return True
            # 壊れた仮想環境を削除
            print(f"  [{provider_name}] 壊れた仮想環境を再作成中...")
            try:
                shutil.rmtree(venv_dir, ignore_errors=True)
            except Exception as e:
                print(f"  [{provider_name}] 仮想環境の削除に失敗: {e}")
                return False
        
        print(f"  [{provider_name}] 仮想環境を作成中...")
        
        try:
            # 仮想環境を作成
            venv.create(venv_dir, with_pip=True)
            
            # pipをアップグレード
            python_exe = self.get_python_executable(provider_name)
            if python_exe.exists():
                result = subprocess.run(
                    [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    print(f"  [{provider_name}] pipのアップグレードに失敗（続行します）")
            
            print(f"  [{provider_name}] 仮想環境を作成しました")
            return True
            
        except subprocess.TimeoutExpired:
            print(f"  [{provider_name}] 仮想環境の作成がタイムアウト")
            return False
        except Exception as e:
            print(f"  [{provider_name}] 仮想環境の作成に失敗: {e}")
            return False
    
    def get_required_packages(self, client_file: Path) -> List[str]:
        """
        クライアントファイルからREQUIRED_PACKAGESを読み取る
        
        Args:
            client_file: クライアントファイルのパス
        
        Returns:
            必要なパッケージのリスト
        """
        try:
            with open(client_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # REQUIRED_PACKAGES = [...] を正規表現で抽出
            pattern = r'REQUIRED_PACKAGES\s*=\s*\[(.*?)\]'
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                return []
            
            # リストの中身をパース
            list_content = match.group(1)
            
            # 文字列リテラルを抽出（シングルクォートとダブルクォート両対応）
            string_pattern = r'["\']([^"\']+)["\']'
            packages = re.findall(string_pattern, list_content)
            
            return packages
            
        except FileNotFoundError:
            print(f"  クライアントファイルが見つかりません: {client_file}")
            return []
        except Exception as e:
            print(f"  REQUIRED_PACKAGES の読み取りエラー: {e}")
            return []
    
    def parse_package_spec(self, package_spec: str) -> Tuple[str, Optional[str]]:
        """
        パッケージ指定を名前とバージョン条件に分解
        
        Args:
            package_spec: パッケージ指定文字列（例: "google-genai>=1.0.0"）
        
        Returns:
            (パッケージ名, バージョン条件) のタプル
        """
        # バージョン指定子のパターン
        version_operators = ['>=', '<=', '==', '!=', '>', '<', '~=']
        
        for op in version_operators:
            if op in package_spec:
                parts = package_spec.split(op, 1)
                return parts[0].strip(), op + parts[1].strip()
        
        # バージョン指定がない場合
        return package_spec.strip(), None
    
    def get_installed_packages(self, provider_name: str) -> Dict[str, str]:
        """
        インストール済みパッケージとバージョンを取得
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            {パッケージ名: バージョン} の辞書
        """
        python_exe = self.get_python_executable(provider_name)
        
        if not python_exe.exists():
            return {}
        
        try:
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {}
            
            packages = json.loads(result.stdout)
            # パッケージ名を小文字に正規化
            return {pkg['name'].lower(): pkg['version'] for pkg in packages}
            
        except subprocess.TimeoutExpired:
            print(f"  [{provider_name}] パッケージ一覧の取得がタイムアウト")
            return {}
        except json.JSONDecodeError:
            print(f"  [{provider_name}] パッケージ一覧のパースに失敗")
            return {}
        except Exception as e:
            print(f"  [{provider_name}] パッケージ一覧の取得に失敗: {e}")
            return {}
    
    def load_cache(self, provider_name: str) -> Dict[str, str]:
        """
        キャッシュを読み込む
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            キャッシュされたパッケージ情報
        """
        cache_file = self.get_cache_file(provider_name)
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # パッケージ名を小文字に正規化
                    return {k.lower(): v for k, v in data.items()}
            except json.JSONDecodeError:
                print(f"  [{provider_name}] キャッシュファイルが破損しています")
            except Exception as e:
                print(f"  [{provider_name}] キャッシュの読み込みに失敗: {e}")
        
        return {}
    
    def save_cache(self, provider_name: str, packages: Dict[str, str]):
        """
        キャッシュを保存
        
        Args:
            provider_name: プロバイダー名
            packages: 保存するパッケージ情報
        """
        cache_file = self.get_cache_file(provider_name)
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(packages, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  [{provider_name}] キャッシュの保存に失敗: {e}")
    
    def install_packages(self, provider_name: str, packages: List[str]) -> bool:
        """
        パッケージをインストール
        
        Args:
            provider_name: プロバイダー名
            packages: インストールするパッケージのリスト
        
        Returns:
            全てのインストールが成功した場合True
        """
        if not packages:
            return True
        
        python_exe = self.get_python_executable(provider_name)
        
        if not python_exe.exists():
            print(f"  [{provider_name}] Python実行ファイルが見つかりません")
            return False
        
        success = True
        
        for package in packages:
            pkg_name, _ = self.parse_package_spec(package)
            print(f"  [{provider_name}] {pkg_name} をインストール中...")
            
            try:
                result = subprocess.run(
                    [str(python_exe), "-m", "pip", "install", package],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    print(f"  [{provider_name}] {pkg_name} のインストールに失敗:")
                    # エラーメッセージを短く表示
                    error_msg = result.stderr.strip()
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    print(f"    {error_msg}")
                    success = False
                else:
                    print(f"  [{provider_name}] {pkg_name} をインストールしました")
                
            except subprocess.TimeoutExpired:
                print(f"  [{provider_name}] {pkg_name} のインストールがタイムアウト（5分）")
                success = False
            except Exception as e:
                print(f"  [{provider_name}] {pkg_name} のインストールエラー: {e}")
                success = False
        
        return success
    
    def check_and_install(self, provider_name: str, client_file: Path) -> bool:
        """
        依存関係をチェックし、必要ならインストール
        
        Args:
            provider_name: プロバイダー名
            client_file: クライアントファイルのパス
        
        Returns:
            依存関係が満たされた場合True
        """
        # 必要なパッケージを取得
        required = self.get_required_packages(client_file)
        
        if not required:
            # REQUIRED_PACKAGES が定義されていない場合は成功とみなす
            return True
        
        print(f"  [{provider_name}] 依存関係をチェック中... ({len(required)}個のパッケージ)")
        
        # 仮想環境を確保
        if not self.ensure_venv(provider_name):
            return False
        
        # キャッシュを確認
        cache = self.load_cache(provider_name)
        
        # 必要なパッケージがキャッシュにあるか確認
        packages_not_in_cache = []
        for pkg_spec in required:
            pkg_name, _ = self.parse_package_spec(pkg_spec)
            if pkg_name.lower() not in cache:
                packages_not_in_cache.append(pkg_spec)
        
        # キャッシュで全て満たされている場合
        if not packages_not_in_cache:
            print(f"  [{provider_name}] 依存関係は既にインストール済み（キャッシュ確認）")
            return True
        
        # 実際にインストール済みか確認
        installed = self.get_installed_packages(provider_name)
        
        packages_to_install = []
        for pkg_spec in required:
            pkg_name, _ = self.parse_package_spec(pkg_spec)
            if pkg_name.lower() not in installed:
                packages_to_install.append(pkg_spec)
        
        # 全てインストール済みの場合
        if not packages_to_install:
            # キャッシュを更新
            self.save_cache(provider_name, installed)
            print(f"  [{provider_name}] 依存関係は既にインストール済み")
            return True
        
        # 不足パッケージをインストール
        print(f"  [{provider_name}] {len(packages_to_install)}個のパッケージをインストールします")
        
        if not self.install_packages(provider_name, packages_to_install):
            print(f"  [{provider_name}] 一部のパッケージのインストールに失敗しました")
            return False
        
        # インストール後のパッケージ一覧を取得してキャッシュ
        installed = self.get_installed_packages(provider_name)
        self.save_cache(provider_name, installed)
        
        print(f"  [{provider_name}] 依存関係のインストール完了")
        return True
    
    def add_venv_to_path(self, provider_name: str) -> bool:
        """
        仮想環境のsite-packagesをsys.pathに追加
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            成功した場合True
        """
        venv_dir = self.get_venv_dir(provider_name)
        
        if not venv_dir.exists():
            return False
        
        # site-packagesのパスを特定
        if self.is_windows:
            site_packages = venv_dir / "Lib" / "site-packages"
        else:
            # Pythonバージョンを取得
            python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            site_packages = venv_dir / "lib" / python_version / "site-packages"
        
        if site_packages.exists():
            site_packages_str = str(site_packages)
            if site_packages_str not in sys.path:
                sys.path.insert(0, site_packages_str)
                print(f"  [{provider_name}] site-packages をパスに追加しました")
            return True
        else:
            print(f"  [{provider_name}] site-packages が見つかりません: {site_packages}")
            return False
    
    def clear_cache(self, provider_name: str) -> bool:
        """
        指定プロバイダーのキャッシュをクリア
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            成功した場合True
        """
        cache_file = self.get_cache_file(provider_name)
        
        if cache_file.exists():
            try:
                cache_file.unlink()
                print(f"  [{provider_name}] キャッシュをクリアしました")
                return True
            except Exception as e:
                print(f"  [{provider_name}] キャッシュのクリアに失敗: {e}")
                return False
        
        return True
    
    def clear_venv(self, provider_name: str) -> bool:
        """
        指定プロバイダーの仮想環境を削除
        
        Args:
            provider_name: プロバイダー名
        
        Returns:
            成功した場合True
        """
        venv_dir = self.get_venv_dir(provider_name)
        
        if venv_dir.exists():
            try:
                shutil.rmtree(venv_dir)
                print(f"  [{provider_name}] 仮想環境を削除しました")
                # キャッシュも削除
                self.clear_cache(provider_name)
                return True
            except Exception as e:
                print(f"  [{provider_name}] 仮想環境の削除に失敗: {e}")
                return False
        
        return True
    
    def reinstall_all(self, provider_name: str, client_file: Path) -> bool:
        """
        仮想環境を再作成し、依存関係を再インストール
        
        Args:
            provider_name: プロバイダー名
            client_file: クライアントファイルのパス
        
        Returns:
            成功した場合True
        """
        print(f"  [{provider_name}] 依存関係を再インストール中...")
        
        # 仮想環境とキャッシュを削除
        self.clear_venv(provider_name)
        
        # 再インストール
        return self.check_and_install(provider_name, client_file)
