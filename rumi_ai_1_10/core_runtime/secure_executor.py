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
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List


@dataclass
class ExecutionResult:
    """実行結果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_mode: str = "unknown"
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


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
            print("=" * 60, file=sys.stderr)
            print("!!! SECURITY WARNING: PERMISSIVE MODE ENABLED !!!", file=sys.stderr)
            print("Pack code may execute on host without Docker isolation.", file=sys.stderr)
            print("This is ONLY acceptable for development.", file=sys.stderr)
            print("Set RUMI_SECURITY_MODE=strict for production.", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
    
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
        container_name = f"rumi-exec-{pack_id}-{phase}-{abs(hash(component_id)) % 10000}"
        
        safe_context = self._sanitize_context(context)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(safe_context, f, ensure_ascii=False, default=str)
            context_file = f.name
        
        try:
            docker_cmd = [
                "docker", "run",
                "--rm",
                "--name", container_name,
                "--network=none",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--read-only",
                "--tmpfs=/tmp:size=64m,noexec,nosuid",
                "--memory=256m",
                "--memory-swap=256m",
                "--cpus=0.5",
                "--pids-limit=50",
                "--user=65534:65534",
                "--ulimit=nproc=50:50",
                "--ulimit=nofile=100:100",
                "-v", f"{component_dir.resolve()}:/component:ro",
                "-v", f"{context_file}:/context.json:ro",
                "-e", f"RUMI_PACK_ID={pack_id}",
                "-e", f"RUMI_COMPONENT_ID={component_id}",
                "-e", f"RUMI_PHASE={phase}",
                "--label", "rumi.managed=true",
                "--label", f"rumi.pack_id={pack_id}",
                "--label", "rumi.type=executor",
                "python:3.11-slim",
                "python", "-c", self._get_executor_script(file_path.name)
            ]
            
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
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
                    execution_mode="container"
                )
            else:
                return ExecutionResult(
                    success=False,
                    error=result.stderr or f"Exit code: {result.returncode}",
                    execution_mode="container"
                )
        
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
                execution_mode="container"
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Container execution failed: {e}",
                execution_mode="container"
            )
        
        finally:
            try:
                os.unlink(context_file)
            except Exception:
                pass
    
    def _get_executor_script(self, filename: str) -> str:
        """コンテナ内で実行するPythonスクリプト"""
        return f'''
import sys
import json

sys.path.insert(0, "/component")

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
    
    def _execute_on_host_with_warning(
        self,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """ホスト上で実行（開発用、警告付き）"""
        warnings = [
            "!!! SECURITY WARNING !!!",
            "Executing Pack code on host without Docker isolation.",
            "This is only acceptable for development.",
            "Set RUMI_SECURITY_MODE=strict and ensure Docker is running for production.",
            f"Pack: {pack_id}, Component: {component_id}, Phase: {phase}"
        ]
        
        for w in warnings:
            print(f"[SecureExecutor] {w}", file=sys.stderr)
        
        try:
            import importlib.util
            module_name = f"rumi_exec_{pack_id}_{phase}_{abs(hash(str(file_path)))}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            
            if spec is None or spec.loader is None:
                return ExecutionResult(
                    success=False,
                    error=f"Cannot load module: {file_path}",
                    execution_mode="host_permissive",
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
                    warnings=warnings
                )
            
            result = fn(context)
            
            return ExecutionResult(
                success=True,
                output=result,
                execution_mode="host_permissive",
                warnings=warnings
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_mode="host_permissive",
                warnings=warnings
            )
    
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
