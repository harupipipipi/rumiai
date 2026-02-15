"""
secure_executor.py - セキュアなコード実行層

すべてのPackコードはこの層を経由して実行される。
Docker利用可能時はコンテナ内で実行。
利用不可時はセキュリティモードに応じて拒否または警告付き実行。

セキュリティモード（環境変数 RUMI_SECURITY_MODE）:
- strict: Docker必須。利用不可なら実行拒否（デフォルト、本番推奨）
- permissive: Docker利用不可でも警告付きで実行（開発用）
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List


logger = logging.getLogger(__name__)

from .docker_run_builder import DockerRunBuilder
from .paths import LOCAL_PACK_ID, PACK_DATA_BASE_DIR as _PACK_DATA_BASE_DIR

# lib 実行用定数
LIB_INSTALL = "install"
LIB_UPDATE = "update"
PACK_DATA_BASE_DIR = _PACK_DATA_BASE_DIR
# pack_id に許可する文字（英数字、ハイフン、アンダースコアのみ）
PACK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
# ファイル名に許可する文字（英数字、アンダースコア、ハイフン、ドットのみ）(#57)
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')


@dataclass
class ExecutionResult:
    """実行結果（汎用）"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_mode: str = "unknown"
    execution_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    
    # lib 実行用の追加フィールド（オプション）
    pack_id: Optional[str] = None
    lib_type: Optional[str] = None


class SecureExecutor:
    """
    セキュアなコード実行器
    
    Packのsetup.py等をDockerコンテナ内で実行することで、
    ホスト環境を保護する。
    """
    
    MODE_STRICT = "strict"
    MODE_PERMISSIVE = "permissive"
    
    def __init__(self):
        self._docker_available: Optional[bool] = None
        self._lock = threading.Lock()
        self._security_mode = os.environ.get("RUMI_SECURITY_MODE", self.MODE_STRICT).lower()
        
        if self._security_mode not in (self.MODE_STRICT, self.MODE_PERMISSIVE):
            self._security_mode = self.MODE_STRICT
        
        if self._security_mode == self.MODE_PERMISSIVE:
            _warning_msg = (
                "PERMISSIVE MODE ENABLED: Pack code may execute on host "
                "without Docker isolation. This is ONLY acceptable for "
                "development. Set RUMI_SECURITY_MODE=strict for production."
            )
            logger.warning(_warning_msg)
            print("=" * 60, file=sys.stderr)
            print(f"!!! SECURITY WARNING: {_warning_msg}", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
    
    def _sanitize_pack_id(self, pack_id: str) -> tuple:
        """
        pack_id をサニタイズし、安全性を検証
        
        Returns:
            (is_valid: bool, sanitized_or_error: str)
        """
        if not pack_id:
            return False, "pack_id is empty"
        
        # 長さ制限
        if len(pack_id) > 64:
            return False, "pack_id too long (max 64 chars)"
        
        # 許可パターンチェック
        if not PACK_ID_PATTERN.match(pack_id):
            return False, f"pack_id contains invalid characters: {pack_id}"
        
        # 危険なパターン
        if pack_id in ('.', '..') or pack_id.startswith('.'):
            return False, f"pack_id cannot start with dot: {pack_id}"
        
        return True, pack_id
    
    def _ensure_pack_data_dir(self, pack_id: str) -> tuple:
        """
        user_data/packs/{pack_id}/ ディレクトリを作成
        
        Returns:
            (success: bool, path_or_error: Path|str)
        """
        # サニタイズ
        is_valid, result = self._sanitize_pack_id(pack_id)
        if not is_valid:
            return False, result
        
        base_dir = Path(PACK_DATA_BASE_DIR).resolve()
        pack_data_dir = base_dir / pack_id
        
        # パストラバーサル防止
        try:
            pack_data_dir = pack_data_dir.resolve()
            pack_data_dir.relative_to(base_dir)
        except ValueError:
            return False, f"Path traversal detected: {pack_id}"
        
        # ディレクトリ作成
        try:
            pack_data_dir.mkdir(parents=True, exist_ok=True)
            return True, pack_data_dir
        except OSError as e:
            return False, f"Failed to create directory: {e}"
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def is_docker_available(self) -> bool:
        """Docker利用可能性チェック（キャッシュ付き）"""
        if self._docker_available is not None:
            return self._docker_available
        
        with self._lock:
            if self._docker_available is not None:
                return self._docker_available
            
            try:
                result = subprocess.run(
                    ["docker", "info"],
                    capture_output=True,
                    timeout=10
                )
                self._docker_available = result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                self._docker_available = False
        
        return self._docker_available
    
    def get_security_mode(self) -> str:
        """現在のセキュリティモードを取得"""
        return self._security_mode
    
    def execute_component_phase(
        self,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        context: Dict[str, Any],
        component_dir: Path = None,
        timeout: int = 60
    ) -> ExecutionResult:
        """
        コンポーネントフェーズをセキュアに実行
        """
        if not file_path.exists():
            return ExecutionResult(
                success=False,
                error=f"File not found: {file_path}",
                error_type="file_not_found",
                execution_mode="rejected"
            )
        
        if component_dir is None:
            component_dir = file_path.parent
        
        if self.is_docker_available():
            return self._execute_in_container(
                pack_id=pack_id,
                component_id=component_id,
                phase=phase,
                file_path=file_path,
                component_dir=component_dir,
                context=context,
                timeout=timeout
            )
        
        if self._security_mode == self.MODE_STRICT:
            return ExecutionResult(
                success=False,
                error="Docker is required but not available. Set RUMI_SECURITY_MODE=permissive for development.",
                error_type="docker_required",
                execution_mode="rejected"
            )
        
        return self._execute_on_host_with_warning(
            pack_id=pack_id,
            component_id=component_id,
            phase=phase,
            file_path=file_path,
            context=context
        )
    
    def _execute_in_container(
        self,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        component_dir: Path,
        context: Dict[str, Any],
        timeout: int
    ) -> ExecutionResult:
        """Dockerコンテナ内で実行"""
        import time
        start_time = time.time()
        
        container_name = f"rumi-exec-{pack_id}-{phase}-{uuid.uuid4().hex[:12]}"
        
        safe_context = self._sanitize_context(context)
        
        # pip site-packages 確認
        pip_site_packages = None
        _sp = Path(PACK_DATA_BASE_DIR) / pack_id / "python" / "site-packages"
        if _sp.is_dir():
            pip_site_packages = _sp

        pythonpath_value = "/component" + (":/pip-packages" if pip_site_packages else "")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(safe_context, f, ensure_ascii=False, default=str)
            context_file = f.name
        
        try:
            # Docker実行コマンドを構築 (DockerRunBuilder)
            builder = DockerRunBuilder(name=container_name)
            builder.ulimit("nproc=50:50")
            builder.ulimit("nofile=100:100")
            builder.volume(f"{component_dir.resolve()}:/component:ro")
            builder.volume(f"{context_file}:/context.json:ro")
            builder.env("RUMI_PACK_ID", pack_id)
            builder.env("RUMI_COMPONENT_ID", component_id)
            builder.env("RUMI_PHASE", phase)
            builder.env("PYTHONPATH", pythonpath_value)
            builder.label("rumi.managed", "true")
            builder.label("rumi.pack_id", pack_id)
            builder.label("rumi.type", "executor")

            # pip site-packages マウント
            if pip_site_packages:
                builder.volume(f"{pip_site_packages.resolve()}:/pip-packages:ro")

            builder.image("python:3.11-slim")
            builder.command(["python", "-c", self._get_executor_script(file_path.name)])

            docker_cmd = builder.build()
            
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                output = None
                if result.stdout.strip():
                    try:
                        output = json.loads(result.stdout.strip())
                    except json.JSONDecodeError:
                        output = result.stdout.strip()
                
                return ExecutionResult(
                    success=True,
                    output=output,
                    execution_mode="container",
                    execution_time_ms=execution_time_ms
                )
            else:
                return ExecutionResult(
                    success=False,
                    error=result.stderr or f"Exit code: {result.returncode}",
                    error_type="container_execution_error",
                    execution_mode="container",
                    execution_time_ms=execution_time_ms
                )
        
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
                error_type="timeout",
                execution_mode="container",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Container execution failed: {e}",
                error_type=type(e).__name__,
                execution_mode="container",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        finally:
            try:
                os.unlink(context_file)
            except Exception:
                pass
    
    def _get_executor_script(self, filename: str) -> str:
        """コンテナ内で実行するPythonスクリプト"""
        # #57: ファイル名バリデーション
        if not SAFE_FILENAME_PATTERN.match(filename):
            raise ValueError(
                f"Unsafe filename rejected: {filename!r}. "
                f"Only alphanumeric, underscore, hyphen, and dot are allowed."
            )
        return f'''
import sys
import json

sys.path.append("/component")

with open("/context.json", "r") as f:
    context = json.load(f)

target_file = "/component/{filename}"

import importlib.util
spec = importlib.util.spec_from_file_location("target_module", target_file)

if spec and spec.loader:
    module = importlib.util.module_from_spec(spec)
    sys.modules["target_module"] = module
    spec.loader.exec_module(module)
    
    fn = getattr(module, "run", None) or getattr(module, "main", None)
    if fn:
        result = fn(context)
        if result:
            print(json.dumps(result, default=str))
else:
    print(json.dumps({{"error": "Cannot load module"}}))
'''
    
    def _get_lib_executor_script(self, filename: str) -> str:
        """lib実行用のPythonスクリプト"""
        # #57: ファイル名バリデーション
        if not SAFE_FILENAME_PATTERN.match(filename):
            raise ValueError(
                f"Unsafe filename rejected: {filename!r}. "
                f"Only alphanumeric, underscore, hyphen, and dot are allowed."
            )
        return f'''
import sys
import json

sys.path.append("/lib")

with open("/context.json", "r") as f:
    context = json.load(f)

target_file = "/lib/{filename}"

import importlib.util
spec = importlib.util.spec_from_file_location("lib_module", target_file)

if spec and spec.loader:
    module = importlib.util.module_from_spec(spec)
    sys.modules["lib_module"] = module
    spec.loader.exec_module(module)
    
    fn = getattr(module, "run", None)
    if fn:
        import inspect
        sig = inspect.signature(fn)
        if len(sig.parameters) >= 1:
            result = fn(context)
        else:
            result = fn()
        if result:
            print(json.dumps(result, default=str))
        else:
            print(json.dumps({{"status": "completed"}}))
    else:
        print(json.dumps({{"error": "No run function found"}}))
else:
    print(json.dumps({{"error": "Cannot load module"}}))
'''
    
    def execute_lib(
        self,
        pack_id: str,
        lib_type: str,
        lib_file: Path,
        context: Dict[str, Any] = None,
        timeout: int = 120
    ) -> ExecutionResult:
        """
        lib（install/update）をセキュアに実行
        
        Args:
            pack_id: Pack ID
            lib_type: "install" または "update"
            lib_file: lib ファイルのパス
            context: 実行コンテキスト
            timeout: タイムアウト秒数
        
        Returns:
            ExecutionResult（pack_id, lib_type フィールド付き）
        """
        import time
        start_time = time.time()
        
        # local_pack はスキップ
        if pack_id == LOCAL_PACK_ID:
            return ExecutionResult(
                success=False,
                error="local_pack does not support lib execution",
                error_type="local_pack_skip",
                execution_mode="skipped",
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        # pack_id サニタイズ
        is_valid, sanitize_result = self._sanitize_pack_id(pack_id)
        if not is_valid:
            return ExecutionResult(
                success=False,
                error=sanitize_result,
                error_type="invalid_pack_id",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        # ファイル存在確認
        if not lib_file.exists():
            return ExecutionResult(
                success=False,
                error=f"File not found: {lib_file}",
                error_type="file_not_found",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        # lib_type 検証
        if lib_type not in (LIB_INSTALL, LIB_UPDATE):
            return ExecutionResult(
                success=False,
                error=f"Invalid lib_type: {lib_type}",
                error_type="invalid_lib_type",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        # Pack データディレクトリ作成
        dir_ok, dir_result = self._ensure_pack_data_dir(pack_id)
        if not dir_ok:
            return ExecutionResult(
                success=False,
                error=dir_result,
                error_type="directory_error",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type
            )
        pack_data_dir = dir_result
        
        if self.is_docker_available():
            return self._execute_lib_in_container(
                pack_id=pack_id,
                lib_type=lib_type,
                lib_file=lib_file,
                pack_data_dir=pack_data_dir,
                context=context,
                timeout=timeout,
                start_time=start_time
            )
        
        # Docker 不可
        if self._security_mode == self.MODE_STRICT:
            return ExecutionResult(
                success=False,
                error="Docker is required for lib execution in strict mode",
                error_type="docker_required",
                execution_mode="rejected",
                execution_time_ms=(time.time() - start_time) * 1000,
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        # permissive: 警告付きホスト実行
        return self._execute_lib_on_host_with_warning(
            pack_id=pack_id,
            lib_type=lib_type,
            lib_file=lib_file,
            pack_data_dir=pack_data_dir,
            context=context,
            start_time=start_time
        )
    
    def _execute_lib_in_container(
        self,
        pack_id: str,
        lib_type: str,
        lib_file: Path,
        pack_data_dir: Path,
        context: Dict[str, Any],
        timeout: int,
        start_time: float
    ) -> ExecutionResult:
        """Dockerコンテナ内でlib実行"""
        import time
        
        container_name = f"rumi-lib-{pack_id}-{lib_type}-{uuid.uuid4().hex[:12]}"
        lib_dir = lib_file.parent
        
        # pip site-packages 確認
        pip_site_packages = None
        _sp = Path(PACK_DATA_BASE_DIR) / pack_id / "python" / "site-packages"
        if _sp.is_dir():
            pip_site_packages = _sp

        pythonpath_value = "/lib" + (":/pip-packages" if pip_site_packages else "")
        
        # コンテキスト準備
        exec_context = {
            "pack_id": pack_id,
            "lib_type": lib_type,
            "ts": self._now_ts(),
            "lib_dir": str(lib_dir),
            "data_dir": "/data",  # コンテナ内パス
            **(context or {})
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(exec_context, f, ensure_ascii=False, default=str)
            context_file = f.name
        
        try:
            # Docker実行コマンドを構築 (DockerRunBuilder)
            builder = DockerRunBuilder(name=container_name)
            builder.ulimit("nproc=50:50")
            builder.ulimit("nofile=100:100")
            # lib ディレクトリ（読み取り専用）
            builder.volume(f"{lib_dir.resolve()}:/lib:ro")
            # Pack データディレクトリ（読み書き可能）
            builder.volume(f"{pack_data_dir.resolve()}:/data:rw")
            # コンテキストファイル
            builder.volume(f"{context_file}:/context.json:ro")
            # 環境変数
            builder.env("RUMI_PACK_ID", pack_id)
            builder.env("RUMI_LIB_TYPE", lib_type)
            builder.env("PYTHONPATH", pythonpath_value)
            # ラベル
            builder.label("rumi.managed", "true")
            builder.label("rumi.pack_id", pack_id)
            builder.label("rumi.type", "lib_executor")

            # pip site-packages マウント
            if pip_site_packages:
                builder.volume(f"{pip_site_packages.resolve()}:/pip-packages:ro")

            builder.image("python:3.11-slim")
            builder.command(["python", "-c", self._get_lib_executor_script(lib_file.name)])

            docker_cmd = builder.build()
            
            proc_result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            if proc_result.returncode == 0:
                output = None
                if proc_result.stdout.strip():
                    try:
                        output = json.loads(proc_result.stdout.strip())
                    except json.JSONDecodeError:
                        output = proc_result.stdout.strip()
                
                return ExecutionResult(
                    success=True,
                    output=output,
                    execution_mode="container",
                    execution_time_ms=execution_time_ms,
                    pack_id=pack_id,
                    lib_type=lib_type
                )
            else:
                return ExecutionResult(
                    success=False,
                    error=proc_result.stderr or f"Exit code: {proc_result.returncode}",
                    error_type="container_execution_error",
                    execution_mode="container",
                    execution_time_ms=execution_time_ms,
                    pack_id=pack_id,
                    lib_type=lib_type
                )
        
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            return ExecutionResult(
                success=False,
                error=f"Lib execution timed out after {timeout}s",
                error_type="timeout",
                execution_mode="container",
                execution_time_ms=(time.time() - start_time) * 1000,
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Container execution failed: {e}",
                error_type=type(e).__name__,
                execution_mode="container",
                execution_time_ms=(time.time() - start_time) * 1000,
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        finally:
            try:
                os.unlink(context_file)
            except Exception:
                pass
    
    def _execute_lib_on_host_with_warning(
        self,
        pack_id: str,
        lib_type: str,
        lib_file: Path,
        pack_data_dir: Path,
        context: Dict[str, Any],
        start_time: float
    ) -> ExecutionResult:
        """ホスト上でlib実行（permissiveモード、警告付き）"""
        import time
        
        warnings = [f"Executing lib on host without Docker: Pack={pack_id}, LibType={lib_type}"]
        logger.debug("Permissive host execution: pack=%s lib_type=%s", pack_id, lib_type)
        
        module_name = f"rumi_lib_{pack_id}_{lib_type}_{abs(hash(str(lib_file)))}"
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, str(lib_file))
            
            if spec is None or spec.loader is None:
                return ExecutionResult(
                    success=False,
                    error=f"Cannot load module: {lib_file}",
                    error_type="module_load_error",
                    execution_mode="host_permissive",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    warnings=warnings,
                    pack_id=pack_id,
                    lib_type=lib_type
                )
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            
            # lib ディレクトリを一時的にパスに追加
            lib_dir = str(lib_file.parent)
            if lib_dir not in sys.path:
                sys.path.append(lib_dir)
            
            try:
                spec.loader.exec_module(module)
            finally:
                if lib_dir in sys.path:
                    sys.path.remove(lib_dir)
            
            fn = getattr(module, "run", None)
            if fn is None:
                return ExecutionResult(
                    success=False,
                    error=f"No 'run' function found in {lib_file}",
                    error_type="no_run_function",
                    execution_mode="host_permissive",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    warnings=warnings,
                    pack_id=pack_id,
                    lib_type=lib_type
                )
            
            # コンテキスト準備
            exec_context = {
                "pack_id": pack_id,
                "lib_type": lib_type,
                "ts": self._now_ts(),
                "lib_dir": str(lib_file.parent),
                "data_dir": str(pack_data_dir),
                **(context or {})
            }
            
            import inspect
            sig = inspect.signature(fn)
            
            if len(sig.parameters) >= 1:
                output = fn(exec_context)
            else:
                output = fn()
            
            return ExecutionResult(
                success=True,
                output=output,
                execution_mode="host_permissive",
                execution_time_ms=(time.time() - start_time) * 1000,
                warnings=warnings,
                pack_id=pack_id,
                lib_type=lib_type
            )
            
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                execution_mode="host_permissive",
                execution_time_ms=(time.time() - start_time) * 1000,
                warnings=warnings,
                pack_id=pack_id,
                lib_type=lib_type
            )
        
        finally:
            if module_name in sys.modules:
                del sys.modules[module_name]
    
    def _execute_on_host_with_warning(
        self,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """ホスト上で実行（開発用、警告付き）"""
        import time
        start_time = time.time()
        
        warnings = [
            f"SECURITY WARNING: Executing on host without Docker isolation: "
            f"Pack={pack_id}, Component={component_id}, Phase={phase}",
            "本番環境ではDocker隔離を使用してください (RUMI_SECURITY_MODE=strict)。"
            " permissiveモードは開発環境専用です。",
        ]
        logger.warning(
            "SECURITY: Host execution without Docker isolation — "
            "pack=%s component=%s phase=%s. "
            "Use RUMI_SECURITY_MODE=strict with Docker for production.",
            pack_id, component_id, phase
        )
        
        module_name = f"rumi_exec_{pack_id}_{phase}_{abs(hash(str(file_path)))}"
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            
            if spec is None or spec.loader is None:
                return ExecutionResult(
                    success=False,
                    error=f"Cannot load module: {file_path}",
                    error_type="module_load_error",
                    execution_mode="host_permissive",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    warnings=warnings
                )
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            fn = getattr(module, "run", None) or getattr(module, "main", None)
            if fn is None:
                return ExecutionResult(
                    success=True,
                    output=None,
                    execution_mode="host_permissive",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    warnings=warnings
                )
            
            result = fn(context)
            
            return ExecutionResult(
                success=True,
                output=result,
                execution_mode="host_permissive",
                execution_time_ms=(time.time() - start_time) * 1000,
                warnings=warnings
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                execution_mode="host_permissive",
                execution_time_ms=(time.time() - start_time) * 1000,
                warnings=warnings
            )
        
        finally:
            if module_name in sys.modules:
                del sys.modules[module_name]
    
    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """コンテキストから安全なフィールドのみ抽出"""
        safe_keys = {
            "phase", "ts", "ids", "paths",
            "_source_component", "chat_id", "payload"
        }
        
        safe_context = {}
        for key in safe_keys:
            if key in context:
                value = context[key]
                try:
                    json.dumps(value, default=str)
                    safe_context[key] = value
                except (TypeError, ValueError):
                    pass
        
        return safe_context


_global_secure_executor: Optional[SecureExecutor] = None
_executor_lock = threading.Lock()


def get_secure_executor() -> SecureExecutor:
    """グローバルなSecureExecutorを取得"""
    global _global_secure_executor
    if _global_secure_executor is None:
        with _executor_lock:
            if _global_secure_executor is None:
                _global_secure_executor = SecureExecutor()
    return _global_secure_executor


def reset_secure_executor() -> SecureExecutor:
    """SecureExecutorをリセット（テスト用）"""
    global _global_secure_executor
    with _executor_lock:
        _global_secure_executor = SecureExecutor()
    return _global_secure_executor
