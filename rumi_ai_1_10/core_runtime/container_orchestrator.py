"""
container_orchestrator.py - Dockerコンテナオーケストレーション

Packごとのコンテナ管理を行う。
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ContainerResult:
    """コンテナ操作結果"""
    success: bool
    container_id: Optional[str] = None
    error: Optional[str] = None


class ContainerOrchestrator:
    """Dockerコンテナオーケストレータ"""
    
    def __init__(
        self,
        packs_dir: str = "ecosystem/packs",
        docker_dir: str = "docker/core"
    ):
        self.packs_dir = Path(packs_dir)
        self.docker_dir = Path(docker_dir)
        self._containers: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._docker_available: Optional[bool] = None
    
    def is_docker_available(self) -> bool:
        """Docker利用可能性チェック"""
        if self._docker_available is not None:
            return self._docker_available
        
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10
            )
            self._docker_available = result.returncode == 0
        except Exception:
            self._docker_available = False
        
        return self._docker_available
    
    def start_container(self, pack_id: str, timeout: int = 30) -> ContainerResult:
        """Packのコンテナを起動"""
        if not self.is_docker_available():
            return ContainerResult(success=False, error="Docker not available")
        
        container_name = f"rumi-pack-{pack_id}"
        
        with self._lock:
            if pack_id in self._containers:
                return ContainerResult(success=True, container_id=self._containers[pack_id])
        
        try:
            check = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.ID}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if check.stdout.strip():
                subprocess.run(
                    ["docker", "start", container_name],
                    capture_output=True,
                    timeout=timeout
                )
                container_id = check.stdout.strip()
            else:
                result = subprocess.run(
                    [
                        "docker", "run", "-d",
                        "--name", container_name,
                        "--memory", "128m",
                        "--cpus", "0.5",
                        "--read-only",
                        "--tmpfs", "/tmp:size=64m",
                        "--security-opt", "no-new-privileges:true",
                        "--label", f"rumi.pack_id={pack_id}",
                        "--label", "rumi.managed=true",
                        f"rumi-pack-{pack_id}:latest"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                if result.returncode != 0:
                    return ContainerResult(success=False, error=result.stderr)
                
                container_id = result.stdout.strip()
            
            with self._lock:
                self._containers[pack_id] = container_id
            
            return ContainerResult(success=True, container_id=container_id)
            
        except subprocess.TimeoutExpired:
            return ContainerResult(success=False, error="Container start timed out")
        except Exception as e:
            return ContainerResult(success=False, error=str(e))
    
    def stop_container(self, pack_id: str) -> ContainerResult:
        """コンテナを停止"""
        container_name = f"rumi-pack-{pack_id}"
        
        try:
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                timeout=30
            )
            
            with self._lock:
                self._containers.pop(pack_id, None)
            
            return ContainerResult(success=True)
        except Exception as e:
            return ContainerResult(success=False, error=str(e))
    
    def remove_container(self, pack_id: str) -> ContainerResult:
        """コンテナを削除"""
        container_name = f"rumi-pack-{pack_id}"
        
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                timeout=30
            )
            
            with self._lock:
                self._containers.pop(pack_id, None)
            
            return ContainerResult(success=True)
        except Exception as e:
            return ContainerResult(success=False, error=str(e))
    
    def list_containers(self) -> List[Dict[str, Any]]:
        """管理中のコンテナ一覧"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", "label=rumi.managed=true", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            containers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            
            return containers
        except Exception:
            return []


_global_orchestrator: Optional[ContainerOrchestrator] = None
_co_lock = threading.Lock()


def get_container_orchestrator() -> ContainerOrchestrator:
    """グローバルなContainerOrchestratorを取得"""
    global _global_orchestrator
    if _global_orchestrator is None:
        with _co_lock:
            if _global_orchestrator is None:
                _global_orchestrator = ContainerOrchestrator()
    return _global_orchestrator


def initialize_container_orchestrator() -> ContainerOrchestrator:
    """ContainerOrchestratorを初期化"""
    global _global_orchestrator
    with _co_lock:
        _global_orchestrator = ContainerOrchestrator()
    return _global_orchestrator
