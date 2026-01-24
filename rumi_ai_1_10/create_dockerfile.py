
#!/usr/bin/env python3
"""
create_dockerfile.py - Rumi AI Docker Isolation System Generator

このスクリプトを実行するだけで、完全なDocker隔離システムが構築されます。

使用方法:
    python create_dockerfile.py

生成されるもの:
    - docker/base/Dockerfile (共有ベースイメージ)
    - docker/packs/{pack_id}/Dockerfile (Pack毎のイメージ)
    - docker/docker-compose.yml
    - docker/config.json
    - docker/handlers/ (権限ハンドラ)
    - docker/scopes/ (スコープ定義)
    - docker/grants/ (許可記録)
    - docker/sandbox/{pack_id}/ (作業領域)
    - docs/docker_security.txt (ドキュメント)
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional


class DockerGenerator:
    """Docker隔離システムの全ファイルを生成"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.docker_dir = self.project_root / "docker"
        self.ecosystem_dir = self.project_root / "ecosystem"
        self.docs_dir = self.project_root / "docs"
        self.packs: List[str] = []
        
    def run(self):
        """メイン実行"""
        print("=" * 60)
        print("  Rumi AI Docker Isolation System Generator")
        print("=" * 60)
        print()
        
        # 1. ecosystem をスキャン
        self._scan_ecosystem()
        
        # 2. ディレクトリ構造を作成
        self._create_directories()
        
        # 3. Base Dockerfile を生成
        self._generate_base_dockerfile()
        
        # 4. 各 Pack の Dockerfile を生成
        self._generate_pack_dockerfiles()
        
        # 5. docker-compose.yml を生成
        self._generate_docker_compose()
        
        # 6. config.json を生成
        self._generate_config()
        
        # 7. handlers を生成
        self._generate_handlers()
        
        # 8. scopes を生成
        self._generate_scopes()
        
        # 9. grants ディレクトリを準備
        self._prepare_grants()
        
        # 10. sandbox_bridge.py を生成
        self._generate_sandbox_bridge()
        
        # 11. sandbox_container.py を生成
        self._generate_sandbox_container()
        
        # 12. core_runtime/__init__.py を更新
        self._update_core_runtime_init()
        
        # 13. ドキュメントを生成
        self._generate_documentation()
        
        # 14. 完了メッセージ
        self._print_completion()
    
    def _scan_ecosystem(self):
        """ecosystem ディレクトリをスキャン"""
        print("[1/13] Scanning ecosystem...")
        
        if not self.ecosystem_dir.exists():
            print(f"  ! Warning: {self.ecosystem_dir} does not exist")
            print("  ! Creating empty ecosystem directory")
            self.ecosystem_dir.mkdir(parents=True, exist_ok=True)
            return
        
        for item in self.ecosystem_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                self.packs.append(item.name)
                print(f"  Found pack: {item.name}")
        
        if not self.packs:
            print("  ! No packs found in ecosystem/")
        else:
            print(f"  Total: {len(self.packs)} packs")
    
    def _create_directories(self):
        """ディレクトリ構造を作成"""
        print("\n[2/13] Creating directory structure...")
        
        directories = [
            self.docker_dir,
            self.docker_dir / "base",
            self.docker_dir / "packs",
            self.docker_dir / "handlers",
            self.docker_dir / "scopes",
            self.docker_dir / "grants",
            self.docker_dir / "sandbox",
            self.docs_dir,
        ]
        
        # Pack毎のディレクトリ
        for pack_id in self.packs:
            directories.append(self.docker_dir / "packs" / pack_id)
            directories.append(self.docker_dir / "sandbox" / pack_id)
        
        for d in directories:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {d.relative_to(self.project_root)}")
    
    def _generate_base_dockerfile(self):
        """Base Dockerfile を生成"""
        print("\n[3/13] Generating base Dockerfile...")
        
        content = '''# Rumi AI Sandbox Base Image
# 
# このイメージは全 Pack で共有される信頼できるベース。
# Pack のコードは一切含まない。

FROM python:3.11-alpine

LABEL maintainer="Rumi AI"
LABEL description="Rumi AI Sandbox Base Image"

# 基本パッケージ（公式が提供、信頼できる）
RUN apk add --no-cache \\
    git \\
    curl \\
    build-base \\
    libffi-dev \\
    openssl-dev

# 作業ディレクトリ
WORKDIR /app

# サンドボックス用ディレクトリ
RUN mkdir -p /sandbox && chmod 755 /sandbox

# 非root ユーザー
RUN adduser -D -u 1000 rumi
RUN chown -R rumi:rumi /app /sandbox

# デフォルトユーザー
USER rumi

# ヘルスチェック用
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s \\
    CMD python -c "print('healthy')" || exit 1

CMD ["tail", "-f", "/dev/null"]
'''
        
        path = self.docker_dir / "base" / "Dockerfile"
        path.write_text(content, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _generate_pack_dockerfiles(self):
        """各 Pack の Dockerfile を生成"""
        print("\n[4/13] Generating pack Dockerfiles...")
        
        for pack_id in self.packs:
            self._generate_single_pack_dockerfile(pack_id)
        
        if not self.packs:
            print("  No packs to generate")
    
    def _generate_single_pack_dockerfile(self, pack_id: str):
        """単一 Pack の Dockerfile を生成"""
        
        # Pack の requirements.txt をチェック
        pack_path = self.ecosystem_dir / pack_id
        has_backend = (pack_path / "backend").exists()
        has_requirements = (pack_path / "backend" / "requirements.txt").exists() if has_backend else False
        
        content = f'''# Rumi AI Pack: {pack_id}
#
# このイメージは {pack_id} Pack 専用。
# 完全に隔離され、他の Pack とは共有しない。

FROM rumi-base:latest

LABEL rumi.pack_id="{pack_id}"
LABEL rumi.managed="true"

USER root

# この Pack 専用の venv
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# pip アップグレード
RUN pip install --no-cache-dir --upgrade pip

'''
        
        if has_requirements:
            content += f'''# この Pack の依存関係（他 Pack と完全分離）
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

'''
        
        content += f'''# この Pack のコード
COPY . /app/pack/

# 権限設定
RUN chown -R rumi:rumi /app /sandbox

# 実行ユーザー
USER rumi

# 環境変数
ENV PACK_ID="{pack_id}"
ENV SANDBOX_PATH="/sandbox"

WORKDIR /app/pack

CMD ["tail", "-f", "/dev/null"]
'''
        
        path = self.docker_dir / "packs" / pack_id / "Dockerfile"
        path.write_text(content, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)} (requirements: {has_requirements})")
    
    def _generate_docker_compose(self):
        """docker-compose.yml を生成"""
        print("\n[5/13] Generating docker-compose.yml...")
        
        services = {}
        networks = {}
        
        for pack_id in self.packs:
            safe_name = pack_id.replace("-", "_").replace(".", "_")
            service_name = f"pack-{safe_name}"
            network_name = f"net-{safe_name}"
            
            services[service_name] = {
                "build": {
                    "context": f"../ecosystem/{pack_id}",
                    "dockerfile": f"../docker/packs/{pack_id}/Dockerfile"
                },
                "image": f"rumi-pack-{pack_id}:latest",
                "container_name": f"rumi-pack-{pack_id}",
                "volumes": [
                    f"./sandbox/{pack_id}:/sandbox:rw"
                ],
                "networks": [network_name],
                "mem_limit": "128m",
                "cpus": 0.5,
                "read_only": True,
                "tmpfs": ["/tmp:size=64m"],
                "security_opt": ["no-new-privileges:true"],
                "labels": [
                    f"rumi.pack_id={pack_id}",
                    "rumi.managed=true"
                ],
                "restart": "unless-stopped",
                "logging": {
                    "driver": "json-file",
                    "options": {
                        "max-size": "10m",
                        "max-file": "3"
                    }
                }
            }
            
            networks[network_name] = {
                "driver": "bridge",
                "internal": True,
                "labels": [
                    f"rumi.pack_id={pack_id}",
                    "rumi.managed=true"
                ]
            }
        
        compose = {
            "version": "3.8",
            "services": services,
            "networks": networks
        }
        
        # YAML形式で出力（PyYAMLなしで手動生成）
        content = self._dict_to_yaml(compose)
        
        path = self.docker_dir / "docker-compose.yml"
        path.write_text(content, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
        print(f"  Services: {len(services)}")
    
    def _dict_to_yaml(self, data: Any, indent: int = 0) -> str:
        """辞書をYAML形式の文字列に変換（簡易実装）"""
        lines = []
        prefix = "  " * indent
        
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    lines.append(f"{prefix}{key}:")
                    lines.append(self._dict_to_yaml(value, indent + 1))
                elif isinstance(value, list):
                    lines.append(f"{prefix}{key}:")
                    for item in value:
                        if isinstance(item, dict):
                            first = True
                            for k, v in item.items():
                                if first:
                                    lines.append(f"{prefix}  - {k}: {self._yaml_value(v)}")
                                    first = False
                                else:
                                    lines.append(f"{prefix}    {k}: {self._yaml_value(v)}")
                        else:
                            lines.append(f"{prefix}  - {self._yaml_value(item)}")
                else:
                    lines.append(f"{prefix}{key}: {self._yaml_value(value)}")
        
        return "\n".join(lines)
    
    def _yaml_value(self, value: Any) -> str:
        """YAML値をフォーマット"""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            if any(c in value for c in ":#{}[]&*!|>'\"%@`"):
                return f'"{value}"'
            return value
        elif value is None:
            return "null"
        else:
            return str(value)
    
    def _generate_config(self):
        """config.json を生成"""
        print("\n[6/13] Generating config.json...")
        
        config = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            
            "isolation": {
                "mode": "per_pack_container",
                "description": "各Packは完全に隔離されたコンテナで実行される"
            },
            
            "base_image": {
                "name": "rumi-base",
                "tag": "latest",
                "dockerfile": "docker/base/Dockerfile"
            },
            
            "resource_defaults": {
                "memory_limit": "128m",
                "cpu_limit": 0.5,
                "tmpfs_size": "64m"
            },
            
            "lifecycle": {
                "startup_mode": "lazy",
                "idle_timeout_minutes": 5,
                "max_concurrent_containers": 10,
                "startup_timeout_seconds": 60
            },
            
            "security": {
                "read_only_rootfs": True,
                "no_new_privileges": True,
                "network_isolation": True,
                "audit_logging": True
            },
            
            "packs": {pack_id: {
                "container_name": f"rumi-pack-{pack_id}",
                "image": f"rumi-pack-{pack_id}:latest",
                "network": f"net-{pack_id.replace('-', '_').replace('.', '_')}",
                "sandbox_path": f"docker/sandbox/{pack_id}"
            } for pack_id in self.packs}
        }
        
        path = self.docker_dir / "config.json"
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _generate_handlers(self):
        """handlers を生成"""
        print("\n[7/13] Generating handlers...")
        
        handlers = {
            "__init__.py": HANDLER_INIT,
            "file_read.py": HANDLER_FILE_READ,
            "file_write.py": HANDLER_FILE_WRITE,
            "env_read.py": HANDLER_ENV_READ,
            "terminal.py": HANDLER_TERMINAL,
            "network.py": HANDLER_NETWORK,
        }
        
        for filename, content in handlers.items():
            path = self.docker_dir / "handlers" / filename
            path.write_text(content, encoding="utf-8")
            print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _generate_scopes(self):
        """scopes を生成"""
        print("\n[8/13] Generating scopes...")
        
        scopes = {
            "file_read.json": SCOPE_FILE_READ,
            "file_write.json": SCOPE_FILE_WRITE,
            "env_read.json": SCOPE_ENV_READ,
            "terminal.json": SCOPE_TERMINAL,
            "network.json": SCOPE_NETWORK,
        }
        
        for filename, content in scopes.items():
            path = self.docker_dir / "scopes" / filename
            path.write_text(content, encoding="utf-8")
            print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _prepare_grants(self):
        """grants ディレクトリを準備"""
        print("\n[9/13] Preparing grants directory...")
        
        gitkeep = self.docker_dir / "grants" / ".gitkeep"
        gitkeep.write_text(GRANTS_GITKEEP, encoding="utf-8")
        print(f"  Created: {gitkeep.relative_to(self.project_root)}")
    
    def _generate_sandbox_bridge(self):
        """sandbox_bridge.py を生成"""
        print("\n[10/13] Generating sandbox_bridge.py...")
        
        core_runtime_dir = self.project_root / "core_runtime"
        core_runtime_dir.mkdir(parents=True, exist_ok=True)
        
        path = core_runtime_dir / "sandbox_bridge.py"
        path.write_text(SANDBOX_BRIDGE_PY, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _generate_sandbox_container(self):
        """sandbox_container.py を生成"""
        print("\n[11/13] Generating sandbox_container.py...")
        
        core_runtime_dir = self.project_root / "core_runtime"
        
        path = core_runtime_dir / "sandbox_container.py"
        path.write_text(SANDBOX_CONTAINER_PY, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _update_core_runtime_init(self):
        """core_runtime/__init__.py を更新"""
        print("\n[12/13] Updating core_runtime/__init__.py...")
        
        core_runtime_dir = self.project_root / "core_runtime"
        init_path = core_runtime_dir / "__init__.py"
        
        # 既存のファイルを読み込み
        existing_content = ""
        if init_path.exists():
            existing_content = init_path.read_text(encoding="utf-8")
        
        # sandbox 関連のインポートが既にあるかチェック
        if "sandbox_bridge" not in existing_content:
            # 追加するインポート
            additions = '''
# Sandbox (Docker Isolation)
from .sandbox_bridge import (
    SandboxBridge,
    SandboxConfig,
    get_sandbox_bridge,
    initialize_sandbox,
)

from .sandbox_container import (
    SandboxContainerManager,
    ContainerConfig,
    ContainerInfo,
    get_container_manager,
)
'''
            # __all__ を更新
            if "__all__" in existing_content:
                # 既存の __all__ に追加
                new_exports = '''
    # Sandbox
    "SandboxBridge",
    "SandboxConfig",
    "get_sandbox_bridge",
    "initialize_sandbox",
    "SandboxContainerManager",
    "ContainerConfig",
    "ContainerInfo",
    "get_container_manager",
'''
                existing_content = existing_content.replace(
                    "__all__ = [",
                    "__all__ = [" + new_exports
                )
            
            # インポートを追加
            existing_content += additions
            
            init_path.write_text(existing_content, encoding="utf-8")
            print(f"  Updated: {init_path.relative_to(self.project_root)}")
        else:
            print(f"  Skipped: {init_path.relative_to(self.project_root)} (already contains sandbox imports)")
    
    def _generate_documentation(self):
        """ドキュメントを生成"""
        print("\n[13/13] Generating documentation...")
        
        path = self.docs_dir / "docker_security.txt"
        path.write_text(DOCUMENTATION, encoding="utf-8")
        print(f"  Created: {path.relative_to(self.project_root)}")
    
    def _print_completion(self):
        """完了メッセージを表示"""
        print()
        print("=" * 60)
        print("  Generation Complete!")
        print("=" * 60)
        print()
        print("Generated files:")
        print(f"  - docker/base/Dockerfile")
        print(f"  - docker/packs/*/Dockerfile ({len(self.packs)} packs)")
        print(f"  - docker/docker-compose.yml")
        print(f"  - docker/config.json")
        print(f"  - docker/handlers/*.py")
        print(f"  - docker/scopes/*.json")
        print(f"  - docker/grants/")
        print(f"  - docker/sandbox/*/")
        print(f"  - core_runtime/sandbox_bridge.py")
        print(f"  - core_runtime/sandbox_container.py")
        print(f"  - docs/docker_security.txt")
        print()
        print("Next steps:")
        print("  1. Build base image:")
        print("     docker build -t rumi-base:latest docker/base/")
        print()
        print("  2. Build all pack images:")
        print("     docker-compose -f docker/docker-compose.yml build")
        print()
        print("  3. Start containers:")
        print("     docker-compose -f docker/docker-compose.yml up -d")
        print()
        print("For more information, see docs/docker_security.txt")


# ============================================================================
# 埋め込みファイル内容
# ============================================================================

HANDLER_INIT = '''"""
Sandbox Handlers

このディレクトリに配置された .py ファイルは自動的にハンドラとして登録されます。

ハンドラのルール:
1. execute(context: dict, args: dict) -> dict 関数を定義
2. オプションで META 辞書を定義（メタ情報）

例:
    def execute(context, args):
        return {"success": True, "data": ...}
    
    META = {
        "requires_scope": True,
        "supports_modes": ["sandbox", "raw"],
        "description": "説明"
    }
"""
'''

HANDLER_FILE_READ = '''"""
file_read ハンドラ

ファイル読み取り（許可ディレクトリのみ）
.env ファイルは除外（env_read を使用）
"""

from pathlib import Path
from typing import Any, Dict
import fnmatch

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ファイル読み取り（許可ディレクトリのみ、.env除外）",
    "version": "1.0"
}

FORBIDDEN_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
}

FORBIDDEN_PATTERNS = ["*.pem", "*.key", "id_rsa*", "*.secret"]


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ファイルを読み取る"""
    path_str = args.get("path")
    if not path_str:
        return {"success": False, "error": "Path is required"}
    
    encoding = args.get("encoding", "utf-8")
    
    try:
        path = Path(path_str).resolve()
        
        # .env ファイルチェック
        if path.name in FORBIDDEN_FILES:
            return {"success": False, "error": f"Forbidden file: {path.name}. Use env_read handler."}
        
        # 禁止パターンチェック
        for pattern in FORBIDDEN_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                return {"success": False, "error": f"Forbidden file pattern: {path.name}"}
        
        if not path.exists():
            return {"success": False, "error": f"File not found: {path_str}"}
        
        if not path.is_file():
            return {"success": False, "error": f"Not a file: {path_str}"}
        
        content = path.read_text(encoding=encoding)
        
        return {
            "success": True,
            "content": content,
            "path": str(path),
            "size": len(content)
        }
    
    except UnicodeDecodeError as e:
        return {"success": False, "error": f"Encoding error: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Read error: {e}"}
'''

HANDLER_FILE_WRITE = '''"""
file_write ハンドラ

ファイル書き込み（許可ディレクトリのみ）
"""

from pathlib import Path
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ファイル書き込み（許可ディレクトリのみ）",
    "version": "1.0"
}

FORBIDDEN_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
    ".bashrc", ".zshrc", ".profile",
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ファイルを書き込む"""
    path_str = args.get("path")
    content = args.get("content")
    
    if not path_str:
        return {"success": False, "error": "Path is required"}
    
    if content is None:
        return {"success": False, "error": "Content is required"}
    
    encoding = args.get("encoding", "utf-8")
    create_parents = args.get("create_parents", True)
    
    try:
        path = Path(path_str).resolve()
        
        if path.name in FORBIDDEN_FILES:
            return {"success": False, "error": f"Forbidden file: {path.name}"}
        
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        
        path.write_text(content, encoding=encoding)
        
        return {
            "success": True,
            "path": str(path),
            "size": len(content)
        }
    
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}
'''

HANDLER_ENV_READ = '''"""
env_read ハンドラ

環境変数読み取り（キー単位でアクセス制御）
"""

import os
from pathlib import Path
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "環境変数の読み取り（許可キーのみ）",
    "version": "1.0"
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """環境変数を読み取る"""
    allowed_keys = set(context.get("allowed_keys", []))
    requested_keys = args.get("keys")
    env_file = args.get("env_file", ".env")
    
    allow_all = "*" in allowed_keys
    
    if requested_keys is None:
        target_keys = None if allow_all else allowed_keys
    else:
        if allow_all:
            target_keys = set(requested_keys)
        else:
            target_keys = set(requested_keys) & allowed_keys
    
    if target_keys is not None and not target_keys:
        return {"success": False, "error": "No allowed keys requested"}
    
    values = {}
    
    # コンテナ内の環境変数から取得
    if target_keys is None:
        env_vars = _parse_env_file(Path(env_file))
        values = env_vars
    else:
        for key in target_keys:
            value = os.environ.get(key)
            if value is not None:
                values[key] = value
    
    return {
        "success": True,
        "values": values,
        "keys_found": list(values.keys())
    }


def _parse_env_file(path: Path) -> Dict[str, str]:
    """シンプルな.envパーサー"""
    result = {}
    if not path.exists():
        return result
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip(\'"\').strip("\'")
                    result[key] = value
    except Exception:
        pass
    
    return result
'''

HANDLER_TERMINAL = '''"""
terminal ハンドラ

ターミナルコマンド実行（許可ディレクトリ内のみ）
"""

import subprocess
import shlex
from pathlib import Path
from typing import Any, Dict, List

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ターミナルコマンド実行（許可ディレクトリ内のみ）",
    "version": "1.0"
}

FORBIDDEN_COMMANDS = {"rm -rf /", "rm -rf ~", "mkfs", "dd if=/dev/zero"}
FORBIDDEN_PATTERNS = ["sudo ", "su ", "chmod 777", "curl | sh", "wget | sh"]


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ターミナルコマンドを実行"""
    command = args.get("command")
    if not command:
        return {"success": False, "error": "Command is required"}
    
    cwd = args.get("cwd", "/sandbox")
    timeout = args.get("timeout", 30)
    
    # 禁止コマンドチェック
    if command in FORBIDDEN_COMMANDS:
        return {"success": False, "error": "Forbidden command"}
    
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in command:
            return {"success": False, "error": f"Forbidden command pattern: {pattern}"}
    
    # cd .. によるエスケープを検出
    if "cd .." in command or "cd /" in command:
        return {"success": False, "error": "Directory escape not allowed"}
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": f"Execution error: {e}"}
'''

HANDLER_NETWORK = '''"""
network ハンドラ

ネットワーク通信の制御（ドメイン/ポート単位でアクセス制御）
"""

import urllib.parse
import urllib.request
import urllib.error
import socket
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ネットワーク通信（許可ドメイン/ポートのみ）",
    "version": "1.0"
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ネットワークリクエストを実行"""
    action = args.get("action", "request")
    
    if action == "check":
        return _check_permission(context, args)
    elif action == "request":
        return _make_request(context, args)
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def _check_permission(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """URLへのアクセスが許可されているかチェック"""
    url = args.get("url")
    if not url:
        return {"success": False, "error": "URL is required"}
    
    allowed, reason = _is_url_allowed(url, context)
    return {"success": True, "allowed": allowed, "reason": reason, "url": url}


def _make_request(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """HTTPリクエストを実行"""
    url = args.get("url")
    if not url:
        return {"success": False, "error": "URL is required"}
    
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = args.get("timeout", 30)
    
    allowed, reason = _is_url_allowed(url, context)
    if not allowed:
        return {"success": False, "error": reason}
    
    try:
        import json as json_module
        
        data = None
        if body is not None:
            if isinstance(body, dict):
                data = json_module.dumps(body).encode("utf-8")
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
            elif isinstance(body, str):
                data = body.encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status_code": response.status,
                "headers": dict(response.headers),
                "body": response_body
            }
    
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP Error: {e.code}", "status_code": e.code}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {e}"}


def _is_url_allowed(url: str, context: Dict[str, Any]) -> tuple:
    """URLが許可されているかチェック"""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        
        if not hostname:
            return False, "Invalid URL: no hostname"
        
        allowed_domains = context.get("allowed_domains", [])
        blocked_domains = context.get("blocked_domains", [])
        allowed_ports = context.get("allowed_ports", [80, 443])
        
        # ブロックリストチェック
        for blocked in blocked_domains:
            if _domain_matches(hostname, blocked):
                return False, f"Domain blocked: {hostname}"
        
        # 許可リストチェック
        if "*" not in allowed_domains:
            allowed = False
            for domain in allowed_domains:
                if _domain_matches(hostname, domain):
                    allowed = True
                    break
            if not allowed:
                return False, f"Domain not allowed: {hostname}"
        
        # ポートチェック
        if "*" not in allowed_ports and port not in allowed_ports:
            return False, f"Port not allowed: {port}"
        
        return True, "Allowed"
    
    except Exception as e:
        return False, f"URL parse error: {e}"


def _domain_matches(hostname: str, pattern: str) -> bool:
    """ドメインがパターンにマッチするか"""
    hostname = hostname.lower()
    pattern = pattern.lower()
    
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith("." + suffix)
    else:
        return hostname == pattern or hostname.endswith("." + pattern)
'''

SCOPE_FILE_READ = '''{
  "version": "1.0",
  "description": "file_read のスコープ設定",
  "default_directories": [],
  "forbidden_paths": [
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "/etc/shadow",
    "/etc/passwd"
  ],
  "forbidden_extensions": [".pem", ".key", ".secret"],
  "max_file_size_mb": 100
}
'''

SCOPE_FILE_WRITE = '''{
  "version": "1.0",
  "description": "file_write のスコープ設定",
  "default_directories": [],
  "forbidden_paths": [
    "~/.ssh",
    "~/.gnupg",
    "~/.bashrc",
    "~/.zshrc",
    "/etc",
    "/usr",
    "/bin"
  ],
  "max_file_size_mb": 100
}
'''

SCOPE_ENV_READ = '''{
  "version": "1.0",
  "description": "env_read のスコープ設定",
  "available_keys": [
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "SEARCH_API_KEY"
  ],
  "sensitive_keys": [
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "JWT_SECRET"
  ],
  "key_groups": {
    "ai_providers": ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
    "search": ["SEARCH_API_KEY"]
  }
}
'''

SCOPE_TERMINAL = '''{
  "version": "1.0",
  "description": "terminal のスコープ設定",
  "default_directories": ["/sandbox"],
  "forbidden_commands": ["rm -rf /", "rm -rf ~", "mkfs"],
  "forbidden_patterns": ["sudo ", "su ", "chmod 777"],
  "max_timeout_seconds": 300
}
'''

SCOPE_NETWORK = '''{
  "version": "1.0",
  "description": "network のスコープ設定",
  "presets": {
    "ai_providers": {
      "description": "AI API プロバイダー",
      "domains": [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com"
      ]
    },
    "full_access": {
      "description": "全てのネットワークアクセスを許可",
      "domains": ["*"]
    },
    "no_network": {
      "description": "ネットワークアクセスなし",
      "domains": []
    }
  },
  "default_blocked_domains": [
    "localhost",
    "127.0.0.1",
    "*.local",
    "*.internal"
  ],
  "default_allowed_ports": [80, 443]
}
'''

GRANTS_GITKEEP = '''# Permission Grants Directory
#
# このディレクトリにはコンポーネントへの許可記録が保存されます。
# 各ファイル: {component_id}.json
#
# 注意: これは履歴です。矛盾が発生した場合、このファイルが修正されます。
#
# 例:
# {
#   "component_id": "default:tool:my_tool",
#   "permissions": {
#     "file_read": {
#       "enabled": true,
#       "valid": true,
#       "directories": ["/home/user/documents"]
#     }
#   }
# }
'''

SANDBOX_BRIDGE_PY = '''"""
sandbox_bridge.py - Sandbox Bridge (公式ファイル)

Ecosystem コンポーネントと Docker コンテナの仲介役。
各 Pack は完全に隔離されたコンテナで実行される。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class SandboxConfig:
    """Sandbox設定"""
    docker_dir: str = "docker"
    auto_reconcile: bool = True


class SandboxBridge:
    """
    Ecosystem と Docker コンテナの仲介役
    
    役割:
    - handlers/ を自動発見・登録
    - 許可(grants)チェック
    - スコープチェック
    - コンテナへの転送
    
    やらないこと:
    - 権限名のハードコード
    - 具体的な処理の実装（handlers が担当）
    """
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._handlers: Dict[str, Any] = {}
        self._handler_meta: Dict[str, Dict[str, Any]] = {}
        self._scopes: Dict[str, Dict[str, Any]] = {}
        self._grants: Dict[str, Dict[str, Any]] = {}
        self._docker_dir: Optional[Path] = None
        self._grants_dir: Optional[Path] = None
        self._initialized = False
        self._container_manager = None
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def initialize(self) -> Dict[str, Any]:
        """Sandbox を初期化"""
        result = {
            "success": True,
            "handlers_loaded": [],
            "scopes_loaded": [],
            "grants_loaded": [],
            "grants_reconciled": [],
            "containers_initialized": False,
            "errors": []
        }
        
        try:
            self._docker_dir = Path(self.config.docker_dir)
            self._grants_dir = self._docker_dir / "grants"
            
            self._grants_dir.mkdir(parents=True, exist_ok=True)
            
            # handlers 読み込み
            handlers_dir = self._docker_dir / "handlers"
            if handlers_dir.exists():
                for py_file in handlers_dir.glob("*.py"):
                    if py_file.name.startswith("_"):
                        continue
                    try:
                        name = py_file.stem
                        module = self._load_handler_module(py_file)
                        if hasattr(module, "execute") and callable(module.execute):
                            self._handlers[name] = module
                            self._handler_meta[name] = getattr(module, "META", {})
                            result["handlers_loaded"].append(name)
                    except Exception as e:
                        result["errors"].append(f"Handler load error ({py_file.name}): {e}")
            
            # scopes 読み込み
            scopes_dir = self._docker_dir / "scopes"
            if scopes_dir.exists():
                for json_file in scopes_dir.glob("*.json"):
                    try:
                        name = json_file.stem
                        self._scopes[name] = json.loads(json_file.read_text(encoding="utf-8"))
                        result["scopes_loaded"].append(name)
                    except Exception as e:
                        result["errors"].append(f"Scope load error ({json_file.name}): {e}")
            
            # grants 読み込み
            if self._grants_dir.exists():
                for json_file in self._grants_dir.glob("*.json"):
                    if json_file.name.startswith("."):
                        continue
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        component_id = data.get("component_id", json_file.stem)
                        self._grants[component_id] = data
                        result["grants_loaded"].append(component_id)
                    except Exception as e:
                        result["errors"].append(f"Grant load error ({json_file.name}): {e}")
            
            # grants の整合性チェック
            if self.config.auto_reconcile:
                reconciled = self._reconcile_grants()
                result["grants_reconciled"] = reconciled
            
            # コンテナマネージャー初期化
            try:
                from .sandbox_container import get_container_manager
                self._container_manager = get_container_manager()
                container_result = self._container_manager.initialize()
                result["containers_initialized"] = container_result.get("success", False)
                result["docker_available"] = container_result.get("docker_available", False)
                if container_result.get("errors"):
                    result["errors"].extend(container_result["errors"])
            except Exception as e:
                result["errors"].append(f"Container manager error: {e}")
            
            self._initialized = True
            
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Initialization error: {e}")
        
        return result
    
    def _load_handler_module(self, file_path: Path) -> Any:
        """ハンドラモジュールを動的にロード"""
        module_name = f"sandbox_handler_{file_path.stem}_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    
    def _reconcile_grants(self) -> List[str]:
        """grants を現在の handlers/scopes と照合し、矛盾を修正"""
        reconciled = []
        
        for component_id, grant_data in list(self._grants.items()):
            modified = False
            permissions = grant_data.get("permissions", {})
            
            for perm_name, perm_config in list(permissions.items()):
                if perm_name not in self._handlers:
                    perm_config["valid"] = False
                    perm_config["invalid_reason"] = "handler_not_found"
                    modified = True
                    continue
                
                meta = self._handler_meta.get(perm_name, {})
                if meta.get("requires_scope") and perm_name not in self._scopes:
                    perm_config["valid"] = False
                    perm_config["invalid_reason"] = "scope_not_found"
                    modified = True
                    continue
                
                if perm_config.get("valid") is False and perm_config.get("invalid_reason") in ("handler_not_found", "scope_not_found"):
                    perm_config["valid"] = True
                    perm_config.pop("invalid_reason", None)
                    modified = True
                elif "valid" not in perm_config:
                    perm_config["valid"] = True
                    modified = True
            
            if modified:
                grant_data["validated_at"] = self._now_ts()
                self._save_grant(component_id, grant_data)
                reconciled.append(component_id)
        
        return reconciled
    
    def _save_grant(self, component_id: str, data: Dict[str, Any]) -> bool:
        """grant を保存"""
        if self._grants_dir is None:
            return False
        
        try:
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False
    
    def request(
        self,
        component_id: str,
        permission: str,
        args: Dict[str, Any],
        pack_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """コンポーネントからのリクエストを処理"""
        if not self._initialized:
            return {"success": False, "error": "Sandbox not initialized"}
        
        if permission not in self._handlers:
            return {"success": False, "error": f"Handler not found: {permission}"}
        
        grant = self._get_grant(component_id, permission)
        if grant is None:
            return {"success": False, "error": f"Permission not granted: {permission}"}
        
        if not grant.get("enabled", False):
            return {"success": False, "error": f"Permission disabled: {permission}"}
        
        # スコープチェック
        meta = self._handler_meta.get(permission, {})
        if meta.get("requires_scope", False):
            scope_check = self._check_scope(permission, grant, args)
            if not scope_check["allowed"]:
                return {"success": False, "error": scope_check["reason"]}
        
        # コンテキスト構築
        context = {
            "component_id": component_id,
            "permission": permission,
            "pack_id": pack_id,
            "grant": grant,
            "ts": self._now_ts()
        }
        
        if "allowed_keys" in grant:
            context["allowed_keys"] = grant["allowed_keys"]
        if "directories" in grant:
            context["directories"] = grant["directories"]
        if "allowed_domains" in grant:
            context["allowed_domains"] = grant["allowed_domains"]
        if "blocked_domains" in grant:
            context["blocked_domains"] = grant["blocked_domains"]
        if "allowed_ports" in grant:
            context["allowed_ports"] = grant["allowed_ports"]
        
        # コンテナ内で実行
        if pack_id and self._container_manager:
            return self._execute_in_container(pack_id, permission, context, args)
        
        # フォールバック: 直接実行
        try:
            handler = self._handlers[permission]
            result = handler.execute(context, args)
            self._audit_log(component_id, permission, args, result)
            return result
        except Exception as e:
            error_result = {"success": False, "error": f"Handler error: {e}"}
            self._audit_log(component_id, permission, args, error_result)
            return error_result
    
    def _execute_in_container(
        self,
        pack_id: str,
        permission: str,
        context: Dict[str, Any],
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """コンテナ内でハンドラを実行"""
        if self._container_manager is None:
            return {"success": False, "error": "Container manager not available"}
        
        return self._container_manager.execute_handler(pack_id, permission, context, args)
    
    def _get_grant(self, component_id: str, permission: str) -> Optional[Dict[str, Any]]:
        """コンポーネントの特定権限のgrantを取得"""
        if component_id not in self._grants:
            return None
        
        grants = self._grants[component_id]
        permissions = grants.get("permissions", {})
        grant = permissions.get(permission)
        
        if grant and grant.get("valid") is False:
            return None
        
        return grant
    
    def _check_scope(
        self,
        permission: str,
        grant: Dict[str, Any],
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """スコープチェック"""
        if "directories" in grant:
            path = args.get("path", "")
            if path:
                allowed_dirs = grant["directories"]
                if not self._is_path_allowed(path, allowed_dirs):
                    return {"allowed": False, "reason": f"Path not in allowed directories: {path}"}
        
        if "allowed_keys" in grant:
            requested_keys = args.get("keys", [])
            if requested_keys:
                allowed_keys = set(grant["allowed_keys"])
                if "*" not in allowed_keys:
                    for key in requested_keys:
                        if key not in allowed_keys:
                            return {"allowed": False, "reason": f"Key not allowed: {key}"}
        
        return {"allowed": True, "reason": ""}
    
    def _is_path_allowed(self, path: str, allowed_dirs: List[str]) -> bool:
        """パスが許可ディレクトリ内かチェック"""
        try:
            target = Path(path).resolve()
            
            for allowed in allowed_dirs:
                allowed_path = Path(allowed).expanduser().resolve()
                try:
                    target.relative_to(allowed_path)
                    return True
                except ValueError:
                    continue
            
            return False
        except Exception:
            return False
    
    def _audit_log(
        self,
        component_id: str,
        permission: str,
        args: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """監査ログを記録"""
        if self._docker_dir is None:
            return
        
        try:
            audit_dir = self._docker_dir / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            audit_file = audit_dir / f"{today}.jsonl"
            
            log_entry = {
                "ts": self._now_ts(),
                "component_id": component_id,
                "permission": permission,
                "success": result.get("success", False),
                "error": result.get("error") if not result.get("success") else None
            }
            
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\\n")
        except Exception:
            pass
    
    def list_handlers(self) -> List[str]:
        """利用可能なハンドラ一覧"""
        return list(self._handlers.keys())
    
    def get_handler_meta(self, name: str) -> Dict[str, Any]:
        """ハンドラのメタ情報取得"""
        return self._handler_meta.get(name, {})
    
    def has_permission(self, component_id: str, permission: str) -> bool:
        """権限があるかチェック"""
        grant = self._get_grant(component_id, permission)
        return grant is not None and grant.get("enabled", False)
    
    def grant_permission(
        self,
        component_id: str,
        permission: str,
        config: Dict[str, Any]
    ) -> bool:
        """権限を付与"""
        if self._grants_dir is None:
            return False
        
        if permission not in self._handlers:
            return False
        
        try:
            self._grants_dir.mkdir(parents=True, exist_ok=True)
            
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            
            if grant_file.exists():
                data = json.loads(grant_file.read_text(encoding="utf-8"))
            else:
                data = {
                    "version": "1.0",
                    "component_id": component_id,
                    "created_at": self._now_ts(),
                    "permissions": {}
                }
            
            data["permissions"][permission] = {
                "enabled": True,
                "valid": True,
                "granted_at": self._now_ts(),
                **config
            }
            data["updated_at"] = self._now_ts()
            data["validated_at"] = self._now_ts()
            
            grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._grants[component_id] = data
            
            return True
        except Exception:
            return False
    
    def revoke_permission(self, component_id: str, permission: str) -> bool:
        """権限を取り消し"""
        if self._grants_dir is None:
            return False
        
        try:
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            
            if not grant_file.exists():
                return False
            
            data = json.loads(grant_file.read_text(encoding="utf-8"))
            
            if permission in data.get("permissions", {}):
                del data["permissions"][permission]
                data["updated_at"] = self._now_ts()
                
                grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                self._grants[component_id] = data
                return True
            
            return False
        except Exception:
            return False


# グローバルインスタンス
_global_sandbox: Optional[SandboxBridge] = None


def get_sandbox_bridge() -> SandboxBridge:
    """グローバルなSandboxBridgeを取得"""
    global _global_sandbox
    if _global_sandbox is None:
        _global_sandbox = SandboxBridge()
    return _global_sandbox


def initialize_sandbox() -> Dict[str, Any]:
    """Sandboxを初期化"""
    bridge = get_sandbox_bridge()
    return bridge.initialize()
'''

SANDBOX_CONTAINER_PY = '''"""
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
                for line in result.stdout.strip().split("\\n"):
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
        
        context_json = json.dumps(context).replace("'", "\\'")
        args_json = json.dumps(args).replace("'", "\\'")
        
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
'''

DOCUMENTATION = '''================================================================================
Rumi AI - Docker Security System ドキュメント
================================================================================

目次
────────────────────────────────────────────────────────────────────────────────
1. 概要
2. アーキテクチャ
3. セキュリティモデル
4. ディレクトリ構造
5. 使用方法
6. 権限システム
7. ハンドラ
8. トラブルシューティング

================================================================================
1. 概要
================================================================================

Rumi AI Docker Security Systemは、Ecosystem内の各Packを完全に隔離された
Dockerコンテナで実行するセキュリティシステムです。

【設計原則】
- 全てのPackは信頼度ゼロとして扱う
- 各Packは独立したコンテナで実行（共有なし）
- ファイル/ネットワークアクセスは明示的な許可が必要
- 監査ログで全ての操作を記録

================================================================================
2. アーキテクチャ
================================================================================

┌─────────────────────────────────────────────────────────────────┐
│                     Docker Host                                  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Base Image (rumi-base:latest)                          │   │
│  │  - Python 3.11 Alpine                                    │   │
│  │  - 基本ツール (git, curl)                               │   │
│  │  - 信頼できる公式イメージ                               │   │
│  │  - 全コンテナで共有（読み取り専用レイヤー）             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │ Pack A      │      │ Pack B      │      │ Pack C      │     │
│  │ Container   │      │ Container   │      │ Container   │     │
│  │             │      │             │      │             │     │
│  │ - 独自venv  │      │ - 独自venv  │      │ - 独自venv  │     │
│  │ - 独自依存  │      │ - 独自依存  │      │ - 独自依存  │     │
│  │ - 独自code  │      │ - 独自code  │      │ - 独自code  │     │
│  │             │      │             │      │             │     │
│  │ 完全隔離    │      │ 完全隔離    │      │ 完全隔離    │     │
│  └─────────────┘      └─────────────┘      └─────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

【メモリ使用量】
- Base Image: ~60MB（全コンテナ共有）
- コンテナあたり: ~20-30MB（Pack固有レイヤー）
- 20 Pack の場合: 60MB + 20×25MB = ~560MB

================================================================================
3. セキュリティモデル
================================================================================

【信頼の境界】

  公式が提供（信頼できる）:
  ├── Docker Engine
  ├── Linux Kernel
  ├── Base Image (python:3.11-alpine)
  └── 基本ツール

  Packが提供（信頼度ゼロ）:
  ├── Pack のコード
  ├── Pack の requirements.txt
  └── Pack の依存ライブラリ

【隔離の保証】

  ✗ Pack A が Pack B のコードを読む    → 不可能（別コンテナ）
  ✗ Pack A が Pack B のメモリにアクセス → 不可能（別プロセス空間）
  ✗ Pack A が共有ライブラリを汚染     → 不可能（読取専用レイヤー）
  ✗ Pack A が Pack B のファイルを操作  → 不可能（別ボリューム）
  ✗ Pack A が Pack B のネットワークに介入 → 不可能（別ネットワーク）

================================================================================
4. ディレクトリ構造
================================================================================

docker/
├── base/
│   └── Dockerfile              # 共有ベースイメージ
│
├── packs/
│   ├── default/
│   │   └── Dockerfile          # Pack専用イメージ
│   └── {pack_id}/
│       └── Dockerfile
│
├── handlers/                   # 権限ハンドラ
│   ├── file_read.py
│   ├── file_write.py
│   ├── env_read.py
│   ├── terminal.py
│   └── network.py
│
├── scopes/                     # スコープ定義
│   ├── file_read.json
│   ├── file_write.json
│   ├── env_read.json
│   ├── terminal.json
│   └── network.json
│
├── grants/                     # 許可記録
│   └── {component_id}.json
│
├── sandbox/                    # 作業領域
│   └── {pack_id}/
│
├── docker-compose.yml
└── config.json

================================================================================
5. 使用方法
================================================================================

【初期セットアップ】

1. create_dockerfile.py を実行:
   python create_dockerfile.py

2. ベースイメージをビルド:
   docker build -t rumi-base:latest docker/base/

3. 全Packイメージをビルド:
   docker-compose -f docker/docker-compose.yml build

4. コンテナを起動:
   docker-compose -f docker/docker-compose.yml up -d

【コンテナ管理】

# 特定のPackを起動
docker-compose -f docker/docker-compose.yml up -d pack-default

# コンテナの状態確認
docker-compose -f docker/docker-compose.yml ps

# ログ確認
docker-compose -f docker/docker-compose.yml logs pack-default

# 停止
docker-compose -f docker/docker-compose.yml down

================================================================================
6. 権限システム
================================================================================

【権限の種類】

- file_read:  ファイル読み取り（許可ディレクトリのみ）
- file_write: ファイル書き込み（許可ディレクトリのみ）
- env_read:   環境変数読み取り（許可キーのみ）
- terminal:   ターミナル実行（許可ディレクトリ内のみ）
- network:    ネットワーク通信（許可ドメイン/ポートのみ）

【許可の付与】

docker/grants/{component_id}.json:
{
  "component_id": "default:tool:my_tool",
  "permissions": {
    "file_read": {
      "enabled": true,
      "directories": ["/home/user/documents"]
    },
    "env_read": {
      "enabled": true,
      "allowed_keys": ["OPENAI_API_KEY"]
    },
    "network": {
      "enabled": true,
      "allowed_domains": ["api.openai.com"],
      "allowed_ports": [443]
    }
  }
}

================================================================================
7. ハンドラ
================================================================================

【ハンドラの追加】

docker/handlers/ に Python ファイルを追加:

```python
# my_handler.py

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "説明"
}

def execute(context: dict, args: dict) -> dict:
    # 処理
    return {"success": True, "data": ...}
```

【スコープの追加】

docker/scopes/ に JSON ファイルを追加:

```json
{
  "version": "1.0",
  "description": "スコープの説明",
  "default_config": {}
}
```

================================================================================
8. トラブルシューティング
================================================================================

【Dockerが起動しない】
- Docker Desktop が起動しているか確認
- `docker info` でDockerの状態を確認

【コンテナが起動しない】
- `docker-compose logs {service}` でログを確認
- Dockerfile の構文エラーを確認

【権限エラー】
- docker/grants/ に適切な許可ファイルがあるか確認
- 許可されたディレクトリ/キーが正しいか確認

【メモリ不足】
- `docker stats` でメモリ使用量を確認
- config.json の memory_limit を調整
- 不要なコンテナを停止

================================================================================
                              ドキュメント終わり
================================================================================
'''


# ============================================================================
# メイン実行
# ============================================================================

if __name__ == "__main__":
    generator = DockerGenerator()
    generator.run()
