"""
sandbox_container.py - Pack別コンテナ管理

各Ecosystem PackをDockerコンテナで完全に分離して実行する。
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ContainerConfig:
    """コンテナ設定"""
    pack_id: str
    image: str = ""
    memory_limit: str = "128m"
    cpu_limit: float = 0.5


@dataclass
class ContainerInfo:
    """コンテナ情報"""
    container_id: str
    pack_id: str
    status: str
    created_at: str
    image: str = ""


class SandboxContainerManager:
    """
    Pack別コンテナ管理
    
    各Ecosystem Packを独立したDockerコンテナで実行する。
    コンテナ間は完全に分離される。
    """
    
    def __init__(self, docker_dir: str = "docker"):
        self.docker_dir = Path(docker_dir)
        self._containers: Dict[str, ContainerInfo] = {}
        self._configs: Dict[str, ContainerConfig] = {}
        self._lock = threading.Lock()
        self._docker_available: Optional[bool] = None
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def is_docker_available(self) -> bool:
        """Dockerが利用可能かチェック"""
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
    
    def initialize(self) -> Dict[str, Any]:
        """コンテナマネージャーを初期化"""
        result = {
            "success": True,
            "docker_available": self.is_docker_available(),
            "packs_found": [],
            "errors": []
        }
        
        if not self.is_docker_available():
            result["success"] = False
            result["errors"].append("Docker is not available")
            return result
        
        # config.json を読み込み
        config_file = self.docker_dir / "config.json"
        if config_file.exists():
            try:
                config_data = json.loads(config_file.read_text(encoding="utf-8"))
                packs = config_data.get("packs", {})
                
                for pack_id, pack_config in packs.items():
                    self._configs[pack_id] = ContainerConfig(
                        pack_id=pack_id,
                        image=pack_config.get("image", f"rumi-pack-{pack_id}:latest"),
                        memory_limit=config_data.get("resource_defaults", {}).get("memory_limit", "128m"),
                        cpu_limit=config_data.get("resource_defaults", {}).get("cpu_limit", 0.5)
                    )
                    result["packs_found"].append(pack_id)
            except Exception as e:
                result["errors"].append(f"Config load error: {e}")
        
        # 既存のコンテナを検出
        self._detect_running_containers()
        
        return result
    
    def _detect_running_containers(self):
        """起動中のRumiコンテナを検出"""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "label=rumi.managed=true", "--format", "{{.ID}}|{{.Names}}|{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 3:
                        container_id, name, status = parts[0], parts[1], parts[2]
                        
                        # rumi-pack-{pack_id} 形式からpack_idを抽出
                        if name.startswith("rumi-pack-"):
                            pack_id = name[10:]  # "rumi-pack-" の長さは10
                            self._containers[pack_id] = ContainerInfo(
                                container_id=container_id,
                                pack_id=pack_id,
                                status="running" if "Up" in status else "stopped",
                                created_at=self._now_ts()
                            )
        except Exception:
            pass
    
    def ensure_container_running(self, pack_id: str) -> Dict[str, Any]:
        """コンテナが起動していることを確認、なければ起動"""
        with self._lock:
            if pack_id in self._containers:
                info = self._containers[pack_id]
                if info.status == "running":
                    return {"success": True, "container_id": info.container_id, "action": "already_running"}
        
        # コンテナを起動
        return self.start_container(pack_id)
    
    def start_container(self, pack_id: str) -> Dict[str, Any]:
        """コンテナを起動"""
        if not self.is_docker_available():
            return {"success": False, "error": "Docker is not available"}
        
        container_name = f"rumi-pack-{pack_id}"
        
        try:
            # 既存のコンテナがあるか確認
            check_result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.ID}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if check_result.stdout.strip():
                # 既存のコンテナを起動
                result = subprocess.run(
                    ["docker", "start", container_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    container_id = check_result.stdout.strip()
                    with self._lock:
                        self._containers[pack_id] = ContainerInfo(
                            container_id=container_id,
                            pack_id=pack_id,
                            status="running",
                            created_at=self._now_ts()
                        )
                    return {"success": True, "container_id": container_id, "action": "started"}
                else:
                    return {"success": False, "error": f"Start failed: {result.stderr}"}
            else:
                # docker-compose で起動
                compose_file = self.docker_dir / "docker-compose.yml"
                service_name = f"pack-{pack_id.replace('-', '_').replace('.', '_')}"
                
                result = subprocess.run(
                    ["docker-compose", "-f", str(compose_file), "up", "-d", service_name],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    # コンテナIDを取得
                    id_result = subprocess.run(
                        ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.ID}}"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    container_id = id_result.stdout.strip() or container_name
                    
                    with self._lock:
                        self._containers[pack_id] = ContainerInfo(
                            container_id=container_id,
                            pack_id=pack_id,
                            status="running",
                            created_at=self._now_ts()
                        )
                    return {"success": True, "container_id": container_id, "action": "created"}
                else:
                    return {"success": False, "error": f"Compose up failed: {result.stderr}"}
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Container start timed out"}
        except Exception as e:
            return {"success": False, "error": f"Start error: {e}"}
    
    def stop_container(self, pack_id: str) -> Dict[str, Any]:
        """コンテナを停止"""
        container_name = f"rumi-pack-{pack_id}"
        
        try:
            result = subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                with self._lock:
                    if pack_id in self._containers:
                        self._containers[pack_id].status = "stopped"
                return {"success": True, "pack_id": pack_id}
            else:
                return {"success": False, "error": f"Stop failed: {result.stderr}"}
        
        except Exception as e:
            return {"success": False, "error": f"Stop error: {e}"}
    
    def execute_handler(
        self,
        pack_id: str,
        handler: str,
        context: Dict[str, Any],
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """コンテナ内でハンドラを実行"""
        # コンテナが起動していることを確認
        ensure_result = self.ensure_container_running(pack_id)
        if not ensure_result.get("success"):
            return ensure_result
        
        container_name = f"rumi-pack-{pack_id}"
        
        context_json = json.dumps(context).replace("'", "\'")
        args_json = json.dumps(args).replace("'", "\'")
        
        exec_script = f"""
import sys
import json
sys.path.insert(0, '/app/pack/backend')
try:
    from handlers.{handler} import execute
    context = json.loads('{context_json}')
    args = json.loads('{args_json}')
    result = execute(context, args)
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}))
"""
        
        try:
            result = subprocess.run(
                ["docker", "exec", container_name, "python", "-c", exec_script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    return {"success": False, "error": f"Invalid JSON response: {result.stdout}"}
            else:
                return {"success": False, "error": result.stderr or "Execution failed"}
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out"}
        except Exception as e:
            return {"success": False, "error": f"Execution error: {e}"}
    
    def get_container_info(self, pack_id: str) -> Optional[ContainerInfo]:
        """コンテナ情報を取得"""
        with self._lock:
            return self._containers.get(pack_id)
    
    def list_containers(self) -> Dict[str, ContainerInfo]:
        """全コンテナ情報を取得"""
        with self._lock:
            return dict(self._containers)


# グローバルインスタンス
_global_container_manager: Optional[SandboxContainerManager] = None


def get_container_manager() -> SandboxContainerManager:
    """グローバルなコンテナマネージャーを取得"""
    global _global_container_manager
    if _global_container_manager is None:
        _global_container_manager = SandboxContainerManager()
    return _global_container_manager
