"""
python_file_executor.py - python_file_call ステップ実行エンジン (UDS Egress Proxy対応)

Flowの python_file_call ステップを実行する。
Pack承認、Modified検出、パス制限、permissiveモード対応を含む。

設計原則:
- 承認されていないPackのコードは実行しない
- Modifiedなpackのコードは実行しない
- 許可されたパス以外のファイルは実行しない
- permissiveモードでは警告付きでホスト実行を許可

UDS Egress Proxy連携:
- strict モードではコンテナは --network=none で実行
- 外部通信は UDS ソケット経由でのみ可能
- rumi_syscall モジュールをコンテナに注入

パス刷新:
- owner_pack → pack_subdir 基準で実行ファイルを解決
- resolved_path が pack_subdir 配下でない場合は拒否（boundary強制）
- owner_pack 未指定は原則拒否（ecosystem/sandbox のみ許可）
- ALLOWED_ROOTS を ecosystem/ 基準に更新

Host Capability Proxy連携:
- principal_id 単位の capability ソケットをコンテナにマウント
- rumi_capability モジュールをコンテナに注入
- permissive モードでも UDS 経由で capability を呼び出し可能

PR-B追加:
- syscall注入の単一ソース化（rumi_syscall固定）（B5）

PR-C追加:
- ExecutionContext に principal_id / capability_sock_path を追加（修正1）
- executor.execute() に principal_id / capability_sock_path 引数を伝播（修正2受け側）
- permissive ホスト実行時に rumi_capability を sys.modules に注入（推奨修正）

pip依存追加:
- docker run に site-packages の RO マウントを追加し、PYTHONPATH に追加
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


from .paths import (
    ECOSYSTEM_DIR,
    PACK_DATA_BASE_DIR,
    discover_pack_locations,
    find_ecosystem_json,
    get_pack_block_dirs,
    is_path_within,
    PackLocation,
)



# ============================================================
# UDS GID ユーティリティ (A-1: --group-add 対応)
# ============================================================

def _read_gid_env(env_name: str) -> Optional[int]:
    """
    環境変数から GID を読み取る。
    不正値 (空文字列, int変換不可) の場合は None を返す (fail-soft)。
    """
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    try:
        gid = int(raw)
        if gid < 0:
            return None
        return gid
    except (ValueError, TypeError):
        return None


def _get_egress_gid() -> Optional[int]:
    return _read_gid_env("RUMI_EGRESS_SOCKET_GID")


def _get_capability_gid() -> Optional[int]:
    return _read_gid_env("RUMI_CAPABILITY_SOCKET_GID")


@dataclass
class ExecutionContext:
    """python_file_call 実行コンテキスト"""
    flow_id: str
    step_id: str
    phase: str
    ts: str
    owner_pack: Optional[str]
    inputs: Dict[str, Any]
    diagnostics_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    permission_proxy: Optional[Any] = None
    principal_id: Optional[str] = None
    capability_sock_path: Optional[Path] = None


@dataclass
class ExecutionResult:
    """python_file_call 実行結果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_mode: str = "unknown"  # "container", "host_permissive", "rejected"
    execution_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)


class PackApprovalChecker:
    """Pack承認状態チェッカー"""

    def __init__(self):
        self._approval_manager = None
        self._lock = threading.Lock()

    def _get_approval_manager(self):
        """ApprovalManagerを遅延取得"""
        if self._approval_manager is None:
            with self._lock:
                if self._approval_manager is None:
                    try:
                        from .approval_manager import get_approval_manager
                        self._approval_manager = get_approval_manager()
                    except ImportError:
                        pass
        return self._approval_manager

    def is_approved(self, pack_id: str) -> Tuple[bool, Optional[str]]:
        """
        Packが承認済みかチェック

        Returns:
            (承認済みか, 拒否理由)
        """
        am = self._get_approval_manager()
        if am is None:
            # ApprovalManagerがない場合はpermissiveとして扱う
            return True, None

        try:
            from .approval_manager import PackStatus
            status = am.get_status(pack_id)

            if status is None:
                return False, f"Pack '{pack_id}' not found in approval registry"

            if status == PackStatus.APPROVED:
                return True, None
            elif status == PackStatus.MODIFIED:
                return False, f"Pack '{pack_id}' has been modified since approval"
            elif status == PackStatus.BLOCKED:
                return False, f"Pack '{pack_id}' is blocked"
            else:
                return False, f"Pack '{pack_id}' is not approved (status: {status.value})"
        except Exception as e:
            return False, f"Approval check failed: {e}"

    def verify_hash(self, pack_id: str) -> Tuple[bool, Optional[str]]:
        """
        Packのハッシュを検証

        Returns:
            (検証成功か, 失敗理由)
        """
        am = self._get_approval_manager()
        if am is None:
            return True, None

        try:
            if am.verify_hash(pack_id):
                return True, None
            else:
                return False, f"Pack '{pack_id}' hash verification failed"
        except Exception as e:
            return False, f"Hash verification error: {e}"


class PathValidator:
    """ファイルパス検証（pack_subdir boundary 強制）"""

    # 許可されるルートディレクトリ
    ALLOWED_ROOTS = [
        "ecosystem",
        "ecosystem/sandbox",
    ]

    def __init__(self, pack_locations: Optional[Dict[str, PackLocation]] = None):
        self._base_dir = Path.cwd()
        self._allowed_absolute: List[Path] = []
        self._pack_locations: Dict[str, PackLocation] = pack_locations or {}
        self._refresh_allowed_paths()

    def _refresh_allowed_paths(self) -> None:
        """許可パスを更新"""
        self._allowed_absolute = []
        for root in self.ALLOWED_ROOTS:
            abs_path = (self._base_dir / root).resolve()
            if abs_path.exists():
                self._allowed_absolute.append(abs_path)

    def add_allowed_root(self, path: str) -> None:
        """許可ルートを追加"""
        abs_path = Path(path).resolve()
        if abs_path not in self._allowed_absolute:
            self._allowed_absolute.append(abs_path)

    def _get_pack_location(self, owner_pack: str) -> Optional[PackLocation]:
        """owner_pack に対応する PackLocation を取得（キャッシュ or 再探索）"""
        if owner_pack in self._pack_locations:
            return self._pack_locations[owner_pack]

        # キャッシュにない場合は discover で再探索
        locations = discover_pack_locations()
        for loc in locations:
            self._pack_locations[loc.pack_id] = loc

        return self._pack_locations.get(owner_pack)

    def validate(self, file_path: str, owner_pack: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        ファイルパスを検証（pack_subdir boundary 強制）

        owner_pack が指定されている場合は pack_subdir 基準で解決し、
        resolved_path が pack_subdir 配下であることを強制する。
        owner_pack 未指定は ecosystem/sandbox のみ許可。

        Args:
            file_path: 検証するパス
            owner_pack: 所有Pack ID（相対パス解決に使用）

        Returns:
            (有効か, エラー理由, 解決済み絶対パス)
        """
        try:
            path = Path(file_path)

            # owner_pack 未指定の場合は原則拒否（sandbox のみ許可）
            if not owner_pack:
                if path.is_absolute():
                    resolved = path.resolve()
                else:
                    resolved = (self._base_dir / file_path).resolve()

                # sandbox 内であれば許可
                sandbox_dir = (self._base_dir / "ecosystem" / "sandbox").resolve()
                if resolved.exists() and resolved.is_file():
                    try:
                        resolved.relative_to(sandbox_dir)
                        return True, None, resolved
                    except ValueError:
                        pass

                return False, "owner_pack is required for python_file_call", None

            # owner_pack から PackLocation を取得
            pack_loc = self._get_pack_location(owner_pack)

            if pack_loc is None:
                return False, f"Pack '{owner_pack}' not found in ecosystem", None

            pack_subdir = pack_loc.pack_subdir

            # パスの解決
            if path.is_absolute():
                resolved = path.resolve()
            else:
                # pack_subdir 基準の候補で解決
                block_dirs = get_pack_block_dirs(pack_subdir)

                candidates = []
                for block_dir in block_dirs:
                    candidates.append(block_dir / file_path)
                # pack_subdir 直下も候補に（ファイルが直接置かれるケース）
                candidates.append(pack_subdir / file_path)

                resolved = None
                for candidate in candidates:
                    if candidate.exists() and candidate.is_file():
                        resolved = candidate.resolve()
                        break

                if resolved is None:
                    first_candidate = candidates[0] if candidates else (pack_subdir / file_path)
                    return False, f"File not found: {first_candidate} (searched {len(candidates)} candidates)", None

            # ファイル存在チェック
            if not resolved.exists():
                return False, f"File not found: {resolved}", None
            if not resolved.is_file():
                return False, f"Not a file: {resolved}", None

            # ALLOWED_ROOTS 内かチェック
            is_allowed = False
            for allowed_root in self._allowed_absolute:
                try:
                    resolved.relative_to(allowed_root)
                    is_allowed = True
                    break
                except ValueError:
                    continue

            if not is_allowed:
                return False, f"Path outside allowed roots: {resolved}", None

            # pack_subdir boundary 強制
            if not is_path_within(resolved, pack_subdir):
                return (
                    False,
                    f"Path outside pack boundary: {resolved} "
                    f"(pack_subdir: {pack_subdir.resolve()})",
                    None,
                )

            return True, None, resolved

        except Exception as e:
            return False, f"Path validation error: {e}", None


class PythonFileExecutor:
    """
    python_file_call 実行エンジン

    Packのpythonファイルを安全に実行する。
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._syspath_lock = threading.Lock()
        self._approval_checker = PackApprovalChecker()
        self._path_validator = PathValidator()
        self._security_mode = os.environ.get("RUMI_SECURITY_MODE", "strict").lower()
        self._uds_proxy_manager = None
        self._syscall_content_cache: Optional[str] = None
        self._capability_content_cache: Optional[str] = None

        if self._security_mode not in ("strict", "permissive"):
            self._security_mode = "strict"

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def get_security_mode(self) -> str:
        """現在のセキュリティモードを取得"""
        return self._security_mode

    def set_uds_proxy_manager(self, manager) -> None:
        """UDSEgressProxyManagerを設定"""
        self._uds_proxy_manager = manager

    def _get_uds_proxy_manager(self):
        """UDSEgressProxyManagerを取得"""
        if self._uds_proxy_manager is None:
            try:
                from .egress_proxy import get_uds_egress_proxy_manager
                self._uds_proxy_manager = get_uds_egress_proxy_manager()
            except ImportError:
                pass
        return self._uds_proxy_manager

    def execute(
        self,
        file_path: str,
        owner_pack: Optional[str],
        input_data: Any,
        context: ExecutionContext,
        principal_id: Optional[str] = None,
        capability_sock_path: Optional[Path] = None,
        timeout_seconds: float = 60.0
    ) -> ExecutionResult:
        """
        pythonファイルを実行

        Args:
            file_path: 実行するファイルパス
            owner_pack: 所有Pack ID
            input_data: 入力データ
            context: 実行コンテキスト
            principal_id: 主体ID（capability用、未指定ならowner_pack）
            capability_sock_path: capability UDSソケットパス
            timeout_seconds: タイムアウト秒数

        Returns:
            ExecutionResult
        """
        import time
        start_time = time.time()

        result = ExecutionResult(success=False)

        # 1. owner_pack 解決
        resolved_pack = owner_pack or self._infer_pack_from_path(file_path)
        if not resolved_pack and not file_path.startswith("ecosystem/sandbox"):
            resolved_pack = owner_pack  # None — PathValidator が拒否

        # principal 強制（v1）: principal は必ず owner_pack に固定
        # FlowStep から principal_id が来ても無視（乱用事故防止）
        effective_principal = resolved_pack
        if principal_id is not None and principal_id != resolved_pack:
            try:
                from .audit_logger import get_audit_logger
                _audit = get_audit_logger()
                _audit.log_security_event(
                    event_type="principal_id_overridden",
                    severity="warning",
                    description=(
                        f"principal_id '{principal_id}' overridden to "
                        f"owner_pack '{resolved_pack}' (v1 principal enforcement)"
                    ),
                    details={
                        "requested_principal": principal_id,
                        "effective_principal": resolved_pack,
                    },
                )
            except Exception:
                pass

        # 2. 承認チェック
        if resolved_pack:
            approved, reason = self._approval_checker.is_approved(resolved_pack)
            if not approved:
                result.error = reason
                result.error_type = "approval_rejected"
                result.execution_mode = "rejected"
                self._record_rejection(context, result, "approval")
                return result

            # ハッシュ検証
            hash_ok, hash_reason = self._approval_checker.verify_hash(resolved_pack)
            if not hash_ok:
                result.error = hash_reason
                result.error_type = "hash_verification_failed"
                result.execution_mode = "rejected"
                self._record_rejection(context, result, "hash")
                return result

        # 3. パス検証
        path_valid, path_error, resolved_path = self._path_validator.validate(file_path, resolved_pack)
        if not path_valid:
            result.error = path_error
            result.error_type = "path_rejected"
            result.execution_mode = "rejected"
            self._record_rejection(context, result, "path")
            return result

        # 4. 実行
        try:
            docker_available = self._check_docker_available()

            if docker_available:
                # strict モード: UDSソケット確保が必須
                uds_manager = self._get_uds_proxy_manager()
                if uds_manager is None and self._security_mode == "strict":
                    result = ExecutionResult(
                        success=False,
                        error="UDS Egress Proxy manager not available in strict mode",
                        error_type="uds_proxy_unavailable",
                        execution_mode="rejected"
                    )
                    self._record_rejection(context, result, "uds_proxy_unavailable")
                    return result

                # UDSソケット確保
                sock_path = None
                if uds_manager and resolved_pack:
                    success, error, sock_path = uds_manager.ensure_pack_socket(resolved_pack)
                    if not success:
                        if self._security_mode == "strict":
                            result = ExecutionResult(
                                success=False,
                                error=f"Failed to ensure UDS socket: {error}",
                                error_type="socket_ensure_failed",
                                execution_mode="rejected"
                            )
                            self._record_rejection(context, result, "socket_ensure_failed")
                            return result
                        else:
                            result.warnings.append(f"Failed to ensure UDS socket: {error}")

                # Docker隔離実行
                result = self._execute_in_container(
                    resolved_path, resolved_pack, input_data, context, timeout_seconds, sock_path, capability_sock_path
                )
                result.execution_mode = "container"
            elif self._security_mode == "permissive":
                # permissive モードではホスト実行（警告付き）
                result = self._execute_on_host(
                    resolved_path, resolved_pack, input_data, context, timeout_seconds, capability_sock_path
                )
                result.execution_mode = "host_permissive"
                result.warnings.append(
                    "SECURITY WARNING: Executed on host without Docker isolation. "
                    "Set RUMI_SECURITY_MODE=strict and ensure Docker is running for production."
                )
            else:
                # strict モードで Docker 不可 → 拒否
                result = ExecutionResult(
                    success=False,
                    error="Docker is required but not available. Cannot execute in strict mode.",
                    error_type="docker_required",
                    execution_mode="rejected"
                )
                self._record_rejection(context, result, "docker_unavailable_strict")
                return result

        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__
            result.execution_mode = "failed"

        result.execution_time_ms = (time.time() - start_time) * 1000

        # 監査ログに実行結果を記録
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_python_file_call(
                flow_id=context.flow_id,
                step_id=context.step_id,
                phase=context.phase,
                owner_pack=resolved_pack or "unknown",
                file_path=file_path,
                success=result.success,
                execution_mode=result.execution_mode,
                execution_time_ms=result.execution_time_ms,
                error=result.error,
                error_type=result.error_type,
                warnings=result.warnings
            )
        except Exception:
            pass  # 監査ログのエラーで処理を止めない

        return result

    def _infer_pack_from_path(self, file_path: str) -> Optional[str]:
        """
        パスからPack IDを推測

        パターン:
          - ecosystem/<pack_id>/...
          - ecosystem/packs/<pack_id>/...  (互換)
        """
        try:
            path = Path(file_path)
            parts = path.parts

            # ecosystem/packs/<pack_id>/... (互換)
            for i, part in enumerate(parts):
                if part == "packs" and i + 1 < len(parts):
                    return parts[i + 1]

            # ecosystem/<pack_id>/... (新構造)
            for i, part in enumerate(parts):
                if part == "ecosystem" and i + 1 < len(parts):
                    next_part = parts[i + 1]
                    if next_part not in ("packs", "sandbox", "flows"):
                        return next_part

            return None
        except Exception:
            return None

    def _check_docker_available(self) -> bool:
        """Docker利用可能性をチェック"""
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_syscall_module_content(self) -> str:
        """
        rumi_syscall モジュールの内容を取得（B5: 単一ソース化）

        優先順位:
        1. core_runtime/rumi_syscall.py（単一ソース - 推奨）
        2. フォールバック: インラインで最小限のsyscallを生成
        """
        # キャッシュがあれば使用
        if self._syscall_content_cache is not None:
            return self._syscall_content_cache

        # 1. 単一ソース: core_runtime/rumi_syscall.py
        try:
            from . import rumi_syscall
            syscall_path = Path(rumi_syscall.__file__)
            if syscall_path.exists():
                content = syscall_path.read_text(encoding="utf-8")
                self._syscall_content_cache = content
                return content
        except (ImportError, AttributeError, OSError):
            pass

        # 2. フォールバック: インラインで最小限のsyscallを生成
        fallback_content = '''
"""rumi_syscall - Rumi AI OS System Call API (minimal fallback)"""
import json, os, socket, struct
from typing import Any, Dict, Optional

SOCKET_PATH = os.environ.get("RUMI_EGRESS_SOCKET", "/run/rumi/egress.sock")
MAX_RESPONSE_SIZE = 4 * 1024 * 1024

class SyscallError(Exception):
    """システムコールエラー"""
    pass

def http_request(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                 body: Optional[str] = None, timeout_seconds: float = 30.0,
                 socket_path: Optional[str] = None) -> Dict[str, Any]:
    sock_path = socket_path or SOCKET_PATH
    timeout = min(float(timeout_seconds), 120.0)
    request = {"method": method.upper(), "url": url, "headers": headers or {},
               "body": body, "timeout_seconds": timeout}
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout + 5)
        sock.connect(sock_path)
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
        sock.sendall(struct.pack(">I", len(payload)) + payload)
        length_data = b""
        while len(length_data) < 4:
            chunk = sock.recv(4 - len(length_data))
            if not chunk: raise SyscallError("Connection closed")
            length_data += chunk
        length = struct.unpack(">I", length_data)[0]
        if length > MAX_RESPONSE_SIZE: raise SyscallError(f"Response too large: {length}")
        data = b""
        while len(data) < length:
            chunk = sock.recv(min(length - len(data), 65536))
            if not chunk: raise SyscallError("Connection closed")
            data += chunk
        return json.loads(data.decode("utf-8"))
    except SyscallError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "error_type": type(e).__name__}
    finally:
        if sock:
            try: sock.close()
            except: pass

def get(url: str, headers=None, timeout_seconds=30.0):
    return http_request("GET", url, headers=headers, timeout_seconds=timeout_seconds)

def post(url: str, body=None, headers=None, timeout_seconds=30.0):
    return http_request("POST", url, headers=headers, body=body, timeout_seconds=timeout_seconds)

def post_json(url: str, data: Any, headers=None, timeout_seconds=30.0):
    h = dict(headers or {}); h["Content-Type"] = "application/json"
    return http_request("POST", url, headers=h, body=json.dumps(data, ensure_ascii=False), timeout_seconds=timeout_seconds)

def put(url: str, body=None, headers=None, timeout_seconds=30.0):
    return http_request("PUT", url, headers=headers, body=body, timeout_seconds=timeout_seconds)

def delete(url: str, headers=None, timeout_seconds=30.0):
    return http_request("DELETE", url, headers=headers, timeout_seconds=timeout_seconds)

def patch(url: str, body=None, headers=None, timeout_seconds=30.0):
    return http_request("PATCH", url, headers=headers, body=body, timeout_seconds=timeout_seconds)

def head(url: str, headers=None, timeout_seconds=30.0):
    return http_request("HEAD", url, headers=headers, timeout_seconds=timeout_seconds)

request = http_request
'''
        self._syscall_content_cache = fallback_content
        return fallback_content

    def _get_capability_module_content(self) -> str:
        """
        rumi_capability モジュールの内容を取得（単一ソース）

        優先順位:
        1. core_runtime/rumi_capability.py（単一ソース）
        2. フォールバック: 空文字列（注入しない）
        """
        if self._capability_content_cache is not None:
            return self._capability_content_cache

        try:
            from . import rumi_capability
            cap_path = Path(rumi_capability.__file__)
            if cap_path.exists():
                content = cap_path.read_text(encoding="utf-8")
                self._capability_content_cache = content
                return content
        except (ImportError, AttributeError, OSError):
            pass

        self._capability_content_cache = ""
        return ""

    def _execute_in_container(
        self,
        file_path: Path,
        owner_pack: Optional[str],
        input_data: Any,
        context: ExecutionContext,
        timeout_seconds: float,
        sock_path: Optional[Path] = None,
        capability_sock_path: Optional[Path] = None,
    ) -> ExecutionResult:
        """
        Dockerコンテナ内でPythonファイルを実行

        docker run --rm --network=none で実行
        外部通信はUDSソケット経由でのみ可能
        capability呼び出しはcapabilityソケット経由でのみ可能
        pip依存はsite-packagesをROマウントしPYTHONPATHに追加
        """
        import subprocess

        result = ExecutionResult(success=False, execution_mode="container")

        # 一意なコンテナ名を生成（UUID使用で衝突回避）
        unique_id = uuid.uuid4().hex[:12]
        container_name = f"rumi-pfc-{owner_pack or 'unknown'}-{unique_id}"


        # Pack data ディレクトリ (inbox 等の読み取り用)
        pack_data_dir = None
        if owner_pack:
            _pd = Path("user_data") / "packs" / owner_pack
            _pd.mkdir(parents=True, exist_ok=True)
            pack_data_dir = _pd

        # site-packages パスを確認 (pip 依存)
        pip_site_packages = None
        if owner_pack:
            _sp = Path(PACK_DATA_BASE_DIR) / owner_pack / "python" / "site-packages"
            if _sp.is_dir():
                pip_site_packages = _sp

        # GID for --group-add (A-1)
        egress_gid = _get_egress_gid()
        capability_gid = _get_capability_gid()

        # PYTHONPATH 構築
        pythonpath_parts = ["/"]
        if pip_site_packages:
            pythonpath_parts.append("/pip-packages")

        # 入力データとコンテキストをJSON化
        exec_context = {
            "flow_id": context.flow_id,
            "step_id": context.step_id,
            "phase": context.phase,
            "ts": context.ts,
            "owner_pack": owner_pack,
            "inputs": input_data,
        }

        # 一時ファイルのパスを事前に初期化
        input_file = None
        script_file = None
        syscall_file = None
        capability_file = None

        try:
            # 一時ファイルに入力データを書き込み
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump({"input_data": input_data, "context": exec_context}, f, ensure_ascii=False, default=str)
                input_file = f.name

            # rumi_syscall モジュールを一時ファイルに書き込み
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(self._get_syscall_module_content())
                syscall_file = f.name

            # rumi_capability モジュールを一時ファイルに書き込み
            cap_content = self._get_capability_module_content()
            if cap_content:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(cap_content)
                    capability_file = f.name

            # 実行スクリプトを生成
            executor_script = self._generate_executor_script(file_path.name)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(executor_script)
                script_file = f.name

            # Docker実行コマンドを構築
            docker_cmd = [
                "docker", "run",
                "--rm",
                "--name", container_name,
                "--network=none",  # ネットワーク隔離（重要！）
                "--cap-drop=ALL",  # 全権限を削除
                "--security-opt=no-new-privileges:true",
                "--read-only",  # 読み取り専用ファイルシステム
                "--tmpfs=/tmp:size=64m,noexec,nosuid",  # 一時領域
                "--memory=256m",
                "--memory-swap=256m",
                "--cpus=0.5",
                "--pids-limit=100",
                "--user=65534:65534",  # nobody ユーザー
                "-v", f"{file_path.parent.resolve()}:/workspace:ro",  # ソースディレクトリ（読み取り専用）
                "-v", f"{input_file}:/input.json:ro",  # 入力ファイル
                "-v", f"{script_file}:/executor.py:ro",  # 実行スクリプト
                "-v", f"{syscall_file}:/rumi_syscall.py:ro",  # syscallモジュール
                "-e", f"PYTHONPATH={':'.join(pythonpath_parts)}",
            ]

            # --group-add for UDS socket access (A-1)
            group_add_gids: set = set()
            if sock_path and sock_path.exists() and egress_gid is not None:
                group_add_gids.add(egress_gid)
            if capability_sock_path and capability_sock_path.exists() and capability_gid is not None:
                group_add_gids.add(capability_gid)

            for gid in sorted(group_add_gids):
                docker_cmd.extend(["--group-add", str(gid)])

            if group_add_gids:
                result.warnings.append(
                    f"Docker --group-add applied: {sorted(group_add_gids)}"
                )


            # pip site-packages マウント（存在する場合）
            if pip_site_packages:
                docker_cmd.extend([
                    "-v", f"{pip_site_packages.resolve()}:/pip-packages:ro",
                ])

            # Pack data マウント（inbox 等の読み取り用）
            if pack_data_dir and pack_data_dir.exists():
                docker_cmd.extend([
                    "-v", f"{pack_data_dir.resolve()}:/data:ro",
                ])


            # UDSソケットマウント（存在する場合）
            if sock_path and sock_path.exists():
                docker_cmd.extend([
                    "-v", f"{sock_path}:/run/rumi/egress.sock:rw",  # UDSソケット（単体マウント）
                ])

            # Capability ソケットマウント（存在する場合）
            if capability_sock_path and capability_sock_path.exists():
                docker_cmd.extend([
                    "-v", f"{capability_sock_path}:/run/rumi/capability.sock:rw",
                ])

            # rumi_capability.py マウント（存在する場合）
            if capability_file:
                docker_cmd.extend([
                    "-v", f"{capability_file}:/rumi_capability.py:ro",
                ])

            docker_cmd.extend([
                "-w", "/workspace",
                "--label", "rumi.managed=true",
                "--label", f"rumi.pack_id={owner_pack or 'unknown'}",
                "--label", "rumi.type=python_file_call",
                "python:3.11-slim",
                "python", "/executor.py", file_path.name
            ])

            # Docker実行
            try:
                proc_result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds
                )

                if proc_result.returncode == 0:
                    # 出力をパース
                    output_text = proc_result.stdout.strip()
                    if output_text:
                        try:
                            result.output = json.loads(output_text)
                        except json.JSONDecodeError:
                            result.output = output_text
                    else:
                        result.output = None

                    result.success = True
                else:
                    result.error = proc_result.stderr or f"Container exited with code {proc_result.returncode}"
                    result.error_type = "container_execution_error"

            except subprocess.TimeoutExpired:
                # タイムアウト時はコンテナを強制停止
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                result.error = f"Execution timed out after {timeout_seconds}s"
                result.error_type = "timeout"

        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__

        finally:
            # 一時ファイルを削除
            for tmp_file in [input_file, script_file, syscall_file, capability_file]:
                if tmp_file is not None:
                    try:
                        os.unlink(tmp_file)
                    except Exception:
                        pass

        return result

    def _generate_executor_script(self, target_filename: str) -> str:
        """コンテナ内で実行するPythonスクリプトを生成"""
        return f'''
import sys
import json
import importlib.util

# rumi_syscall を先にimport可能にする
sys.path.insert(0, "/")

# 入力を読み込み
with open("/input.json", "r") as f:
    data = json.load(f)

input_data = data.get("input_data", {{}})
context = data.get("context", {{}})

# --- B5: Pack API統一 — context にヘルパー関数を注入 ---
import os
try:
    import rumi_syscall

    def _http_request(method, url, headers=None, body=None, timeout_seconds=30.0):
        return rumi_syscall.http_request(
            method, url, headers=headers, body=body,
            timeout_seconds=timeout_seconds
        )

    def _network_check(domain, port):
        return {{"allowed": True, "reason": "Network access controlled by UDS Egress Proxy in container mode"}}

    context["http_request"] = _http_request
    context["network_check"] = _network_check
except ImportError:
    pass

if os.path.exists("/run/rumi/capability.sock"):
    context["capability_socket"] = "/run/rumi/capability.sock"
# --- /B5 ---

# ターゲットモジュールをロード
target_file = "/workspace/{target_filename}"
spec = importlib.util.spec_from_file_location("target_module", target_file)

if spec and spec.loader:
    module = importlib.util.module_from_spec(spec)
    sys.modules["target_module"] = module
    spec.loader.exec_module(module)

    # run関数を探す
    run_fn = getattr(module, "run", None)
    if run_fn:
        import inspect
        sig = inspect.signature(run_fn)
        param_count = len(sig.parameters)

        if param_count >= 2:
            result = run_fn(input_data, context)
        elif param_count == 1:
            result = run_fn(input_data)
        else:
            result = run_fn()

        # 結果を出力
        if result is not None:
            print(json.dumps(result, default=str))
    else:
        print(json.dumps({{"error": "No run function found"}}))
else:
    print(json.dumps({{"error": "Cannot load module"}}))
'''

    def _execute_on_host(
        self,
        file_path: Path,
        owner_pack: Optional[str],
        input_data: Any,
        context: ExecutionContext,
        timeout_seconds: float,
        capability_sock_path: Optional[Path] = None,
    ) -> ExecutionResult:
        """ホスト上で実行（permissiveモード）"""
        result = ExecutionResult(success=False, execution_mode="host_permissive")

        # 警告を出力
        print(f"[PythonFileExecutor] SECURITY WARNING: Executing on host: {file_path}", file=sys.stderr)

        # rumi_capability をPackコードからimport可能にする（best-effort）
        _capability_injected = False
        _prev_env_cap_sock = os.environ.get("RUMI_CAPABILITY_SOCKET")
        try:
            if capability_sock_path and capability_sock_path.exists():
                os.environ["RUMI_CAPABILITY_SOCKET"] = str(capability_sock_path)
            try:
                from . import rumi_capability as _rc_module
                sys.modules["rumi_capability"] = _rc_module
                _capability_injected = True
            except ImportError:
                result.warnings.append(
                    "rumi_capability module not available for host injection"
                )
        except Exception as e:
            result.warnings.append(
                f"Failed to inject rumi_capability for host execution: {e}"
            )

        module_name = f"pfc_{owner_pack or 'unknown'}_{file_path.stem}_{abs(hash(str(file_path)))}"

        try:
            # モジュールをロード
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))

            if spec is None or spec.loader is None:
                result.error = f"Cannot load module from {file_path}"
                result.error_type = "module_load_error"
                return result

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # sys.pathに追加（スレッドセーフ）
            file_dir = str(file_path.parent)
            path_added = False

            with self._syspath_lock:
                if file_dir not in sys.path:
                    sys.path.insert(0, file_dir)
                    path_added = True

            try:
                spec.loader.exec_module(module)
            finally:
                # sys.pathから削除（追加した場合のみ）
                if path_added:
                    with self._syspath_lock:
                        if file_dir in sys.path:
                            sys.path.remove(file_dir)

            # run関数を探す
            run_fn = getattr(module, "run", None)
            if run_fn is None:
                result.error = f"No 'run' function found in {file_path}"
                result.error_type = "no_run_function"
                return result

            # コンテキスト辞書を構築
            exec_context = {
                "flow_id": context.flow_id,
                "step_id": context.step_id,
                "phase": context.phase,
                "ts": context.ts,
                "owner_pack": owner_pack,
                "inputs": input_data,
                "network_check": self._create_network_check_fn(owner_pack),
                "http_request": self._create_proxy_request_fn(owner_pack),
            }

            if capability_sock_path:
                exec_context["capability_socket"] = str(capability_sock_path)

            if context.permission_proxy:
                exec_context["permission_proxy"] = context.permission_proxy

            # 実行
            import inspect
            sig = inspect.signature(run_fn)
            param_count = len(sig.parameters)

            if param_count >= 2:
                output = run_fn(input_data, exec_context)
            elif param_count == 1:
                output = run_fn(input_data)
            else:
                output = run_fn()

            # 出力をJSON互換に変換
            result.output = self._ensure_json_compatible(output)
            result.success = True

        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__
            result.warnings.append(f"Traceback: {traceback.format_exc()[-2000:]}")

        finally:
            # モジュールをクリーンアップ
            if module_name in sys.modules:
                del sys.modules[module_name]
            # rumi_capability 注入のクリーンアップ
            if _capability_injected:
                sys.modules.pop("rumi_capability", None)
            if _prev_env_cap_sock is not None:
                os.environ["RUMI_CAPABILITY_SOCKET"] = _prev_env_cap_sock
            elif "RUMI_CAPABILITY_SOCKET" in os.environ and capability_sock_path:
                os.environ.pop("RUMI_CAPABILITY_SOCKET", None)

        return result

    def _ensure_json_compatible(self, value: Any) -> Any:
        """値をJSON互換に変換"""
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, (list, tuple)):
            return [self._ensure_json_compatible(v) for v in value]

        if isinstance(value, dict):
            return {str(k): self._ensure_json_compatible(v) for k, v in value.items()}

        # その他はstr化
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)

    def _create_network_check_fn(self, owner_pack: Optional[str]) -> Callable:
        """
        ネットワークアクセスチェック関数を作成

        python_file_call内のコードがネットワークアクセス前に
        呼び出すための関数を提供。
        """
        def check_network(domain: str, port: int) -> Dict[str, Any]:
            """
            ネットワークアクセスをチェック

            Args:
                domain: アクセス先ドメイン
                port: アクセス先ポート

            Returns:
                {"allowed": bool, "reason": str}
            """
            if not owner_pack:
                return {"allowed": False, "reason": "No owner_pack specified"}

            try:
                from .network_grant_manager import get_network_grant_manager
                ngm = get_network_grant_manager()
                result = ngm.check_access(owner_pack, domain, port)
                return {
                    "allowed": result.allowed,
                    "reason": result.reason
                }
            except Exception as e:
                return {"allowed": False, "reason": f"Check failed: {e}"}

        return check_network

    def _create_proxy_request_fn(self, owner_pack: Optional[str]) -> Callable:
        """
        プロキシ経由でHTTPリクエストを送信する関数を作成

        python_file_call内のコードから外部通信を行うための関数を提供。
        """
        def proxy_request(
            method: str,
            url: str,
            headers: Dict[str, str] = None,
            body: str = None,
            timeout_seconds: float = 30.0
        ) -> Dict[str, Any]:
            """
            プロキシ経由でHTTPリクエストを送信

            Args:
                method: HTTPメソッド（GET, POST, etc.）
                url: リクエスト先URL
                headers: HTTPヘッダー
                body: リクエストボディ
                timeout_seconds: タイムアウト秒数

            Returns:
                {
                    "success": bool,
                    "status_code": int,
                    "headers": dict,
                    "body": str,
                    "error": str or None,
                    "allowed": bool,
                    "rejection_reason": str or None
                }
            """
            if not owner_pack:
                return {
                    "success": False,
                    "error": "No owner_pack specified",
                    "allowed": False
                }

            try:
                from .egress_proxy import get_egress_proxy, make_proxy_request
                proxy = get_egress_proxy()
                if not proxy.is_running():
                    return {
                        "success": False,
                        "error": "Egress proxy is not running",
                        "allowed": False
                    }

                proxy_url = proxy.get_endpoint()
                result = make_proxy_request(
                    proxy_url=proxy_url,
                    owner_pack=owner_pack,
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout_seconds=timeout_seconds
                )

                return result.to_dict()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "allowed": False
                }

        return proxy_request

    def _record_rejection(
        self,
        context: ExecutionContext,
        result: ExecutionResult,
        rejection_type: str
    ) -> None:
        """拒否を記録（診断と監査ログ両方）"""
        # 診断コールバック
        if context.diagnostics_callback:
            context.diagnostics_callback({
                "type": "python_file_call_rejected",
                "rejection_type": rejection_type,
                "flow_id": context.flow_id,
                "step_id": context.step_id,
                "phase": context.phase,
                "owner_pack": context.owner_pack,
                "error": result.error,
                "ts": context.ts,
            })

        # 監査ログ
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type=f"python_file_call_{rejection_type}_rejected",
                severity="warning",
                description=result.error or f"Rejected due to {rejection_type}",
                pack_id=context.owner_pack,
                details={
                    "flow_id": context.flow_id,
                    "step_id": context.step_id,
                    "phase": context.phase,
                    "rejection_type": rejection_type,
                }
            )
        except Exception:
            pass  # 監査ログのエラーで処理を止めない


# グローバルインスタンス
_global_executor: Optional[PythonFileExecutor] = None
_executor_lock = threading.Lock()


def get_python_file_executor() -> PythonFileExecutor:
    """グローバルなPythonFileExecutorを取得"""
    global _global_executor
    if _global_executor is None:
        with _executor_lock:
            if _global_executor is None:
                _global_executor = PythonFileExecutor()
    return _global_executor


def reset_python_file_executor() -> PythonFileExecutor:
    """PythonFileExecutorをリセット（テスト用）"""
    global _global_executor
    with _executor_lock:
        _global_executor = PythonFileExecutor()
    return _global_executor
