"""
capability_executor.py - Capability 実行エンジン

principal_id × permission_id の要求を受け、
Trust / Grant を検証し、ハンドラーをサブプロセスで実行する。

設計原則:
- Trust（sha256 allowlist）→ Grant（principal×permission）→ 実行 の順で検証
- ハンドラーはサブプロセスで実行（timeout で kill 可能）
- 全操作を監査ログに記録
- Pack への返却は汎用エラー（詳細は監査へ）

Phase D: FunctionRegistry を唯一のレジストリとして統一。
         _unified_execute() が唯一の実行パス。
         calling_convention 分岐による実行方式の選択。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import threading
import shutil
import uuid
import logging
import types
from .flow_context_security import sanitize_user_flow_context
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# function.call: core_pack 判定用
try:
    from .paths import (
        CORE_PACK_ID_PREFIX as _CORE_PACK_ID_PREFIX,
        ECOSYSTEM_DIR as _ECOSYSTEM_DIR,
    )
except ImportError:
    _CORE_PACK_ID_PREFIX = None  # resolved after _load_permissions_config()
    _ECOSYSTEM_DIR = str(Path(__file__).resolve().parent.parent / "ecosystem")

# core_pack ディレクトリパス
try:
    from .paths import CORE_PACK_DIR as _CORE_PACK_DIR
except ImportError:
    _CORE_PACK_DIR = str(Path(__file__).resolve().parent / "core_pack")

# W25.5: DockerRunBuilder (optional, for user function container execution)
try:
    from .docker_run_builder import DockerRunBuilder as _DockerRunBuilder
except ImportError:
    _DockerRunBuilder = None

# FunctionRegistry / FunctionEntry import
try:
    from .function_registry import FunctionRegistry, FunctionEntry
except ImportError:
    FunctionRegistry = None
    FunctionEntry = None

# crypto_utils: compute_file_sha256 (Phase D: D0-3 依存解消)
# def compute_file_sha256 is provided by core_runtime.crypto_utils and re-exported here.
# Prefer the canonical top-level package so editable installs and tests do not
# load a second function object through rumi_ai_1_10.core_runtime.
try:
    from core_runtime.crypto_utils import compute_file_sha256
except ImportError:
    from .crypto_utils import compute_file_sha256
from .rate_limit_store import PersistentRateLimitStore

from typing import Any, Dict, List, Optional

try:
    from .audit_logger import get_audit_logger
except ImportError:
    def get_audit_logger():
        from .audit_logger import get_audit_logger as _get_audit_logger

        return _get_audit_logger()

# レスポンスサイズ上限（1MB）
MAX_RESPONSE_SIZE = 1 * 1024 * 1024

# args 要約の最大長（監査ログ用）
MAX_ARGS_SUMMARY_LENGTH = 500

logger = logging.getLogger(__name__)
FUNCTION_RUNNER_PATH = Path(__file__).with_name("function_runner.py")
TRUSTED_BUILTIN_PACK_IDS = {"defaultspack", "rumi_default_tools_pack"}

# デフォルトタイムアウト
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 300.0


# W25.5: user function execution
DEFAULT_FUNCTION_TIMEOUT = 30.0
FUNCTION_BASE_IMAGE = "python:3.11-slim"

# --- permissions config loading (施策5: No Favoritism) ---
def _load_permissions_config():
    """Load permission constants from config/permissions.json (fallback: None)."""
    config_path = Path(__file__).parent / "config" / "permissions.json"
    if config_path.is_file():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

_permissions_config = _load_permissions_config()

# Resolve _CORE_PACK_ID_PREFIX fallback from config if paths.py import failed
if _CORE_PACK_ID_PREFIX is None:
    _CORE_PACK_ID_PREFIX = (
        (_permissions_config or {}).get("core_pack_id_prefix", "core_")
    )

# flow.run in-process dispatch
FLOW_RUN_PERMISSION_ID = (
    (_permissions_config or {}).get("permission_ids", {}).get("flow_run", "flow.run")
)
MAX_FLOW_CALL_DEPTH = 10

# docker.* in-process dispatch
DOCKER_PERMISSION_IDS: frozenset = frozenset(
    (_permissions_config or {}).get("permission_ids", {}).get(
        "docker", ["docker.run", "docker.exec", "docker.stop", "docker.logs", "docker.list"]
    )
)
DOCKER_RUN_PERMISSION_ID = (
    (_permissions_config or {}).get("permission_ids", {}).get("docker_run", "docker.run")
)

DOCKER_METHOD_MAP = (
    (_permissions_config or {}).get("docker_method_map", {
        "docker.run": "handle_run",
        "docker.exec": "handle_exec",
        "docker.stop": "handle_stop",
        "docker.logs": "handle_logs",
        "docker.list": "handle_list",
    })
)

# Thread-local storage for flow.run call stack
_flow_call_stack_local = threading.local()

# rate limit: secret.get のみ（無限ループ事故防止）
SECRET_GET_PERMISSION_ID = (
    (_permissions_config or {}).get("permission_ids", {}).get("secret_get", "secrets.get")
)
DEFAULT_SECRET_GET_RATE_LIMIT = 60  # 回/分/principal

# calling_convention 有効値
_VALID_CALLING_CONVENTIONS = frozenset({
    "kernel", "subprocess", "block", "python_host",
    "python_docker", "binary", "command",
})


@dataclass
class CapabilityResponse:
    """Capability 実行レスポンス"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "latency_ms": self.latency_ms,
        }


@dataclass
class _HandlerDefAdapter:
    """
    FunctionEntry → HandlerDefinition 互換アダプタ。

    _execute_handler_subprocess() が要求する HandlerDefinition のフィールドを
    FunctionEntry から構築する。
    """
    handler_id: str
    permission_id: str
    entrypoint: str
    handler_dir: Path
    handler_py_path: Path
    is_builtin: bool = False



def _sanitize_error(msg: str) -> str:
    """stderr/エラーメッセージからファイルパス・トレースバック・環境変数情報を除去する。

    RUMI_ENVIRONMENT=development の場合はサニタイズをスキップし、
    開発時のデバッグ情報を維持する。
    """
    if os.environ.get("RUMI_ENVIRONMENT", "").lower() == "development":
        return msg
    # トレースバック行: File "/path/to/file.py", line 123
    msg = re.sub(r'File ".*?", line \d+.*', '<traceback>', msg)
    # ファイルパス: /foo/bar/baz or C:\foo\bar
    msg = re.sub(r'(?:[A-Za-z]:)?[/\\\\](?:[\w.\-]+[/\\\\]){2,}[\w.\-]*', '<path>', msg)
    # 環境変数: FOO_BAR= 形式
    msg = re.sub(r'[A-Z_]{3,}=\S*', '<env>', msg)
    return msg



# --- secure temp directory ---
_SECURE_TMP_DIR: Optional[Path] = None
_secure_tmp_lock = threading.Lock()


def _get_secure_tmp_dir() -> str:
    """user_data/tmp/ 配下に安全な一時ディレクトリを返す（パーミッション 0700）。

    ディレクトリが存在しない場合は作成する。
    """
    global _SECURE_TMP_DIR
    if _SECURE_TMP_DIR is not None and _SECURE_TMP_DIR.is_dir():
        return str(_SECURE_TMP_DIR)
    with _secure_tmp_lock:
        if _SECURE_TMP_DIR is not None and _SECURE_TMP_DIR.is_dir():
            return str(_SECURE_TMP_DIR)
        base = Path(__file__).resolve().parent.parent / "user_data" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(str(base), 0o700)
        _SECURE_TMP_DIR = base
        return str(_SECURE_TMP_DIR)


def _summarize_args(args: Any, max_length: int = MAX_ARGS_SUMMARY_LENGTH) -> str:
    """args を監査ログ用に要約"""
    try:
        s = json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        s = str(args)
    if len(s) > max_length:
        return s[:max_length] + "...(truncated)"
    return s


class CapabilityExecutor:
    """
    Capability 実行エンジン

    要求を受けて:
    1. FunctionRegistry から FunctionEntry を検索
    2. TrustStore で sha256 を検証
    3. GrantManager で principal×permission を検証
    4. calling_convention に応じて実行
    5. 監査ログに記録
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._initialized = False
        self._trust_store = None
        self._grant_manager = None
        self._handler_registry = None  # backward-compat for legacy tests/callers
        self._rate_limit_store = PersistentRateLimitStore()
        self._secret_get_rate_limit = int(
            os.environ.get("RUMI_SECRET_GET_RATE_LIMIT",
                           str(DEFAULT_SECRET_GET_RATE_LIMIT)))
        self._kernel = None  # KernelCore reference for flow.run
        # function.call dispatch 用
        self._function_registry = None
        self._approval_manager = None
        self._permission_manager = None
        # Wave 29: core function handler table
        self._core_function_handlers: Dict[str, str] = (
            (_permissions_config or {}).get("core_function_handlers", {
                "core_docker_capability": "docker_capability_handler",
                "core_desktop_capability": "desktop_capability_handler",
            })
        ).copy()

    def set_kernel(self, kernel) -> None:
        """
        Kernel インスタンスを注入する（flow.run インプロセス実行用）。

        kernel_core._get_capability_proxy() から呼ばれる。
        """
        self._kernel = kernel

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def initialize(self) -> bool:
        """
        コンポーネントを初期化

        Returns:
            初期化が成功したか
        """
        with self._lock:
            if self._initialized:
                return True

            from .capability_trust_store import get_capability_trust_store
            from .capability_grant_manager import get_capability_grant_manager

            try:
                self._trust_store = get_capability_trust_store()
                self._grant_manager = get_capability_grant_manager()

                # Trust store をロード
                self._trust_store.load()

                # function.call dispatch 用サービスを DI コンテナから取得
                try:
                    from .di_container import get_container as _get_di_container
                    _c = _get_di_container()
                    self._function_registry = _c.get_or_none("function_registry")
                    self._approval_manager = _c.get_or_none("approval_manager")
                    self._permission_manager = _c.get_or_none("permission_manager")
                except Exception:
                    logger.debug(
                        "CapabilityExecutor failed to resolve optional DI services",
                        exc_info=True,
                    )

                # Wave 29: core function handler table initialization
                self._core_function_handlers = (
                    (_permissions_config or {}).get("core_function_handlers", {
                        "core_docker_capability": "docker_capability_handler",
                        "core_desktop_capability": "desktop_capability_handler",
                    })
                ).copy()

                self._initialized = True
                return True
            except Exception as exc:
                logger.error("CapabilityExecutor initialization failed: %s", exc)
                return False

    def register_core_handler(self, pack_id: str, di_service_name: str) -> None:
        """core function handler を動的に登録する。"""
        self._core_function_handlers[pack_id] = di_service_name

    # ------------------------------------------------------------------

    def execute(
        self,
        principal_id: str,
        request: Dict[str, Any],
    ) -> CapabilityResponse:
        """
        Capability 要求を実行

        Args:
            principal_id: 主体ID（UDS由来、信頼できる）
            request: リクエスト辞書
                - permission_id: str（必須）
                - args: dict（任意）
                - timeout_seconds: float（任意）
                - request_id: str（任意）

        Returns:
            CapabilityResponse
        """
        start_time = time.time()

        # function.call 早期分岐
        if request.get("type") == "function.call":
            return self._execute_function_call(principal_id, request, start_time)

        # permission_id バリデーション
        permission_id = request.get("permission_id")
        if not permission_id or not isinstance(permission_id, str):
            resp = CapabilityResponse(
                success=False,
                error="Missing or invalid permission_id",
                error_type="invalid_request",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(principal_id, permission_id or "", None, resp,
                        request.get("args", {}), request.get("request_id", ""))
            return resp

        if permission_id == SECRET_GET_PERMISSION_ID and not self._check_rate_limit(principal_id):
            resp = CapabilityResponse(
                success=False,
                error="Rate limited",
                error_type="rate_limited",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(
                principal_id, permission_id, None, resp, request.get("args", {}), request.get("request_id", ""),
                detail_reason=f"Rate limit exceeded ({self._secret_get_rate_limit}/min)",
            )
            return resp

        # FunctionRegistry で解決
        entry = self._resolve_entry(permission_id)
        if entry is not None:
            return self._unified_execute(entry, principal_id, request, start_time)

        # 未登録の permission_id → handler_not_found（フォールバックなし）
        args = request.get("args", {})
        request_id = request.get("request_id", "")
        resp = CapabilityResponse(
            success=False,
            error="Permission denied",
            error_type="handler_not_found",
            latency_ms=(time.time() - start_time) * 1000,
        )
        self._audit(
            principal_id, permission_id, None, resp, args, request_id,
            detail_reason=f"No handler registered for permission_id '{permission_id}'",
        )
        return resp

    # ------------------------------------------------------------------
    # _resolve_entry
    # ------------------------------------------------------------------

    def _resolve_entry(self, permission_id: str):
        """FunctionRegistry を優先し、旧 handler_registry にも後方互換フォールバックする。"""
        fr = self._function_registry
        if fr is None:
            registry = getattr(self, "_handler_registry", None)
            if registry is None:
                return None
            try:
                candidate = registry.get_by_permission_id(permission_id)
                return self._coerce_legacy_entry(candidate, permission_id)
            except Exception:
                logger.debug("Legacy handler registry lookup failed for '%s'", permission_id, exc_info=True)
                return None
        try:
            get_by_permission_id = getattr(fr, "get_by_permission_id", None)
            if callable(get_by_permission_id):
                entry = get_by_permission_id(permission_id)
                if entry is not None and isinstance(getattr(entry, "qualified_name", None), str):
                    return entry
            entry = fr.resolve_by_alias(permission_id)
            if entry is not None:
                return entry
        except Exception:
            logger.debug("FunctionRegistry lookup failed for '%s'", permission_id, exc_info=True)
        registry = getattr(self, "_handler_registry", None)
        if registry is not None:
            try:
                candidate = registry.get_by_permission_id(permission_id)
                return self._coerce_legacy_entry(candidate, permission_id)
            except Exception:
                logger.debug("Legacy handler registry fallback failed for '%s'", permission_id, exc_info=True)
        return None

    def _coerce_legacy_entry(self, candidate, permission_id: str):
        """旧 handler registry の定義を FunctionEntry 互換の最小 shape に寄せる。"""
        if candidate is None:
            return None
        handler_id = getattr(candidate, "handler_id", None)
        entrypoint = getattr(candidate, "entrypoint", None)
        if not isinstance(handler_id, str) or not isinstance(getattr(candidate, "permission_id", None), str):
            return None
        if entrypoint is not None and not isinstance(entrypoint, str):
            return None
        handler_dir = getattr(candidate, "handler_dir", None) or Path(".")
        handler_py_path = getattr(candidate, "handler_py_path", None)
        is_builtin = bool(getattr(candidate, "is_builtin", False))
        pack_id = getattr(candidate, "pack_id", None)
        if not pack_id:
            pack_id = f"{_CORE_PACK_ID_PREFIX}legacy" if is_builtin else "legacy_pack"
        main_py_path = getattr(candidate, "main_py_path", None) or handler_py_path
        grant_config = getattr(candidate, "grant_config", {})
        qualified_name = getattr(candidate, "qualified_name", None) or handler_id
        calling_convention = getattr(candidate, "calling_convention", None)
        function_dir = getattr(candidate, "function_dir", None) or handler_dir
        vocab_aliases = getattr(candidate, "vocab_aliases", None) or [permission_id]
        return types.SimpleNamespace(
            qualified_name=qualified_name,
            pack_id=pack_id,
            main_py_path=main_py_path,
            grant_config=grant_config,
            calling_convention=calling_convention,
            entrypoint=entrypoint,
            function_dir=function_dir,
            is_builtin=is_builtin,
            legacy_handler_builtin=is_builtin,
            vocab_aliases=vocab_aliases,
        )

    @staticmethod
    def _entry_grant_config(entry):
        grant_config = getattr(entry, "grant_config", None)
        if grant_config is None:
            manifest = getattr(entry, "manifest", None)
            if isinstance(manifest, dict):
                grant_config = manifest.get("grant_config")
        return grant_config

    @staticmethod
    def _is_bundled_builtin_pack_dir(pack_dir: Path, pack_id: str | None = None) -> bool:
        try:
            resolved = pack_dir.resolve()
        except OSError:
            resolved = pack_dir
        ecosystem_root = None
        if _ECOSYSTEM_DIR:
            try:
                ecosystem_root = Path(_ECOSYSTEM_DIR).resolve()
            except OSError:
                ecosystem_root = Path(_ECOSYSTEM_DIR)
        if ecosystem_root is not None:
            try:
                relative = resolved.relative_to(ecosystem_root)
            except ValueError:
                return False
            if not relative.parts:
                return False
            if pack_id and relative.parts[0] != pack_id:
                return False
            return True
        if pack_id and resolved.name != pack_id:
            return False
        return resolved.parent.name == "ecosystem"

    def _is_bundled_core_pack_entry(self, entry) -> bool:
        """Return True only for entries shipped from core_runtime/core_pack/<pack_id>."""
        pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        if not pack_id.startswith(_CORE_PACK_ID_PREFIX):
            return False

        try:
            core_pack_root = Path(_CORE_PACK_DIR).resolve()
        except (OSError, TypeError):
            core_pack_root = Path(_CORE_PACK_DIR)

        entry_paths = [
            getattr(entry, "function_dir", None),
            getattr(entry, "main_py_path", None),
        ]
        for raw_path in entry_paths:
            if raw_path is None:
                continue
            try:
                candidate = Path(raw_path).resolve()
                relative = candidate.relative_to(core_pack_root)
            except (OSError, TypeError, ValueError):
                continue
            if relative.parts and relative.parts[0] == pack_id:
                return True
        return False

    def _entry_path_looks_like_ecosystem_pack(self, entry, pack_id: str) -> bool:
        entry_paths = [
            getattr(entry, "function_dir", None),
            getattr(entry, "main_py_path", None),
        ]
        ecosystem_root = None
        if _ECOSYSTEM_DIR:
            try:
                ecosystem_root = Path(_ECOSYSTEM_DIR).resolve()
            except (OSError, TypeError):
                ecosystem_root = Path(_ECOSYSTEM_DIR)
        for raw_path in entry_paths:
            if raw_path is None:
                continue
            try:
                candidate = Path(raw_path).resolve()
            except (OSError, TypeError):
                continue
            if ecosystem_root is not None:
                try:
                    relative = candidate.relative_to(ecosystem_root)
                except ValueError:
                    pass
                else:
                    if relative.parts and relative.parts[0] == pack_id:
                        return True
            parts = candidate.parts
            for index, part in enumerate(parts[:-1]):
                if part == "ecosystem" and parts[index + 1] == pack_id:
                    return True
        return False

    def _is_core_builtin_trust_bypass_entry(self, entry) -> bool:
        """Preserve legacy core handler compatibility without trusting ecosystem metadata."""
        pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        if bool(getattr(entry, "legacy_handler_builtin", False)):
            return True
        if self._is_bundled_core_pack_entry(entry):
            return True
        if not pack_id.startswith(_CORE_PACK_ID_PREFIX):
            return False
        if pack_id in self._core_function_handlers:
            return True
        return not self._entry_path_looks_like_ecosystem_pack(entry, pack_id)

    def _trusted_builtin_pack_path_verdict(self, pack_id: str, pack_root_hint=None) -> bool | None:
        """Return True/False for an existing path hint, or None when no path evidence exists."""
        normalized_pack_id = str(pack_id or "").strip()
        if normalized_pack_id not in TRUSTED_BUILTIN_PACK_IDS or pack_root_hint is None:
            return None
        try:
            candidate_path = Path(pack_root_hint)
            if not candidate_path.exists():
                return None
            if candidate_path.is_file():
                candidate_path = candidate_path.parent
            return self._is_bundled_builtin_pack_dir(candidate_path, normalized_pack_id)
        except (OSError, TypeError):
            return None

    def _is_trusted_builtin_pack(self, pack_id: str, pack_root_hint=None) -> bool:
        normalized_pack_id = str(pack_id or "").strip()
        if normalized_pack_id not in TRUSTED_BUILTIN_PACK_IDS:
            return False

        path_verdict = self._trusted_builtin_pack_path_verdict(normalized_pack_id, pack_root_hint)
        if path_verdict is not None:
            return path_verdict

        approval_manager = getattr(self, "_approval_manager", None)
        helper = getattr(approval_manager, "_is_trusted_builtin_pack", None)
        if callable(helper):
            try:
                return bool(helper(normalized_pack_id))
            except Exception:
                logger.debug(
                    "approval_manager trusted builtin lookup failed for '%s'",
                    normalized_pack_id,
                    exc_info=True,
                )
        return False

    def _dev_auto_reapprove_pack(self, pack_id: str) -> bool:
        if str(os.environ.get("RUMI_ENVIRONMENT", "")).lower() not in {"development", "dev"}:
            return False
        if str(os.environ.get("RUMI_AUTO_APPROVE_LOCAL", "")).lower() != "true":
            return False
        approval_manager = getattr(self, "_approval_manager", None)
        if approval_manager is None:
            return False
        try:
            scan_packs = getattr(approval_manager, "scan_packs", None)
            if callable(scan_packs):
                scan_packs()
            result = approval_manager.approve(pack_id)
            return bool(getattr(result, "success", False))
        except Exception:
            logger.debug("dev auto reapprove failed for pack '%s'", pack_id, exc_info=True)
            return False

    def _has_permission_via_runtime_or_grant(self, principal_id: str, permission_id: str) -> bool:
        permission_manager = getattr(self, "_permission_manager", None)
        if permission_manager is not None:
            try:
                if permission_manager.has_permission(principal_id, permission_id):
                    return True
            except Exception:
                logger.debug(
                    "permission_manager.has_permission failed for '%s' / '%s'",
                    principal_id,
                    permission_id,
                    exc_info=True,
                )
        grant_manager = getattr(self, "_grant_manager", None)
        if grant_manager is not None:
            try:
                result = grant_manager.check(principal_id, permission_id)
                return getattr(result, "allowed", None) is True
            except Exception:
                logger.debug(
                    "grant_manager.check failed for '%s' / '%s'",
                    principal_id,
                    permission_id,
                    exc_info=True,
                )
        return False

    @staticmethod
    def _core_docker_permission_id(function_id: str) -> Optional[str]:
        method_name = f"handle_{function_id}"
        for permission_id, mapped_method in DOCKER_METHOD_MAP.items():
            if mapped_method == method_name:
                return permission_id
        return None

    def _authorized_core_dispatch_config(
        self,
        principal_id: str,
        entry,
        start_time: float,
    ) -> tuple[bool, Optional[CapabilityResponse], Dict[str, Any]]:
        """Authorize privileged in-process core dispatch and return signed grant config."""
        if entry.pack_id != "core_docker_capability":
            return True, None, dict(self._entry_grant_config(entry) or {})

        permission_id = self._core_docker_permission_id(entry.function_id)
        if permission_id is None:
            return True, None, {}

        grant_manager = getattr(self, "_grant_manager", None)
        if grant_manager is None:
            resp = CapabilityResponse(
                success=False,
                error="Permission denied",
                error_type="grant_denied",
                latency_ms=(time.time() - start_time) * 1000,
            )
            return False, resp, {}

        try:
            grant_result = grant_manager.check(principal_id, permission_id)
        except Exception:
            logger.debug(
                "grant_manager.check failed for function.call core dispatch '%s' / '%s'",
                principal_id,
                permission_id,
                exc_info=True,
            )
            resp = CapabilityResponse(
                success=False,
                error="Permission denied",
                error_type="grant_denied",
                latency_ms=(time.time() - start_time) * 1000,
            )
            return False, resp, {}

        if not getattr(grant_result, "allowed", False):
            resp = CapabilityResponse(
                success=False,
                error="Permission denied",
                error_type="grant_denied",
                latency_ms=(time.time() - start_time) * 1000,
            )
            return False, resp, {}

        config = getattr(grant_result, "config", None)
        return True, None, dict(config) if isinstance(config, dict) else {}

    # ------------------------------------------------------------------
    # _unified_execute
    # ------------------------------------------------------------------

    def _unified_execute(self, entry, principal_id, request, start_time):
        """FunctionEntry ベースで統一された実行パス。"""
        effective_permission_id = None
        if entry.vocab_aliases:
            effective_permission_id = entry.vocab_aliases[0]
        if not effective_permission_id:
            effective_permission_id = entry.qualified_name

        args = request.get("args", {})
        request_context = request.get("context") if isinstance(request.get("context"), dict) else None
        timeout_seconds = min(float(request.get("timeout_seconds", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        request_id = request.get("request_id", "")
        handler_id = entry.qualified_name

        # 1. rate limit チェック（secrets.get のみ）
        if effective_permission_id == SECRET_GET_PERMISSION_ID:
            if not self._check_rate_limit(principal_id):
                resp = CapabilityResponse(success=False, error="Rate limited", error_type="rate_limited",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            detail_reason=f"Rate limit exceeded ({self._secret_get_rate_limit}/min)")
                return resp

        # 初期化チェック
        if not self._initialized:
            if not self.initialize():
                resp = CapabilityResponse(success=False, error="Capability system failed to initialize",
                                          error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id)
                return resp

        # 2. Trust チェック
        # Only core entries loaded from the bundled core_pack tree may bypass the
        # normal trust-store check.  A pack_id prefix alone is attacker-controlled
        # metadata for imported ecosystem packs.
        is_builtin = self._is_core_builtin_trust_bypass_entry(entry)
        builtin_sha256 = None

        if is_builtin:
            if entry.main_py_path and Path(entry.main_py_path).is_file():
                try:
                    builtin_sha256 = compute_file_sha256(Path(entry.main_py_path))
                except Exception:
                    builtin_sha256 = "compute_failed"
        else:
            if not entry.main_py_path or not Path(entry.main_py_path).is_file():
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason="main_py_path not found for trust verification")
                return resp
            try:
                actual_sha256 = compute_file_sha256(Path(entry.main_py_path))
            except Exception:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason="Failed to compute handler sha256 at execution time")
                return resp
            trust_result = self._trust_store.is_trusted(handler_id, actual_sha256)
            if not trust_result.trusted:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason=trust_result.reason)
                return resp

        # 3. Function manifest requirement checks
        pack_id = getattr(entry, "pack_id", "")
        pack_root_hint = getattr(entry, "function_dir", None) or getattr(entry, "main_py_path", None)
        is_trusted_builtin = self._is_trusted_builtin_pack(pack_id, pack_root_hint=pack_root_hint)
        principal_is_trusted_builtin = self._is_trusted_builtin_pack(principal_id)
        if not principal_is_trusted_builtin and principal_id == pack_id:
            principal_is_trusted_builtin = is_trusted_builtin

        requires = getattr(entry, "requires", None) or []
        if not (is_builtin or is_trusted_builtin) and requires:
            for req_perm in requires:
                if not self._has_permission_via_runtime_or_grant(pack_id, req_perm):
                    resp = CapabilityResponse(success=False,
                                              error=f"Function requires permission '{req_perm}' not granted to pack '{pack_id}'",
                                              error_type="requires_denied", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                                trusted=True, detail_reason=f"Pack '{pack_id}' lacks required permission '{req_perm}'")
                    return resp

        caller_requires = getattr(entry, "caller_requires", None) or []
        if caller_requires:
            caller_ok = False
            high_risk_approval_only = self._caller_requires_high_risk_approval_only(caller_requires)
            if (
                not high_risk_approval_only
                and self._permission_manager is not None
                and hasattr(self._permission_manager, "check_caller_requires")
            ):
                caller_ok = self._permission_manager.check_caller_requires(principal_id, caller_requires)
            if not caller_ok and self._request_context_satisfies_caller_requires(
                principal_id,
                caller_requires,
                request_context,
                principal_is_trusted_builtin=principal_is_trusted_builtin,
            ):
                caller_ok = True
            if not caller_ok:
                resp = CapabilityResponse(success=False, error="Caller does not meet caller_requires",
                                          error_type="caller_requires_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=True, detail_reason=f"Principal '{principal_id}' does not meet caller_requires: {caller_requires}")
                return resp

        # 4. Grant チェック
        # FunctionRegistry entries must preserve the legacy capability boundary:
        # every principal × permission execution requires an explicit grant, even
        # when the function manifest omits optional grant_config schema metadata.
        grant_result = self._grant_manager.check(principal_id, effective_permission_id)
        if not grant_result.allowed:
            resp = CapabilityResponse(success=False, error="Permission denied", error_type="grant_denied",
                                      latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                        trusted=True, grant_allowed=False, grant_reason=grant_result.reason)
            return resp
        grant_config = grant_result.config or {}

        # 5. calling_convention 分岐
        calling_convention = getattr(entry, "calling_convention", None)
        if calling_convention and calling_convention in _VALID_CALLING_CONVENTIONS:
            resp = self._dispatch_by_calling_convention(
                calling_convention=calling_convention, entry=entry, principal_id=principal_id,
                effective_permission_id=effective_permission_id, grant_config=grant_config,
                args=args, timeout_seconds=timeout_seconds, request_id=request_id, start_time=start_time)
        else:
            resp = self._dispatch_by_permission_id(
                entry=entry, principal_id=principal_id, effective_permission_id=effective_permission_id,
                grant_config=grant_config, args=args, timeout_seconds=timeout_seconds,
                request_id=request_id, start_time=start_time)

        # 6. 監査
        extra = {"unified_path": True}
        if is_builtin:
            extra["builtin_sha256"] = builtin_sha256
        if calling_convention:
            extra["calling_convention"] = calling_convention
        self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                    trusted=True, grant_allowed=True, grant_reason="Granted", extra_details=extra)
        return resp

    # ------------------------------------------------------------------
    # _dispatch_by_calling_convention
    # ------------------------------------------------------------------

    def _dispatch_by_calling_convention(self, calling_convention, entry, principal_id,
                                         effective_permission_id, grant_config, args,
                                         timeout_seconds, request_id, start_time,
                                         request_context=None):
        """calling_convention の値で実行パスを分岐する。"""
        if calling_convention == "kernel":
            return CapabilityResponse(
                success=False, error="kernel calling_convention functions must be invoked via kernel handler dispatch, not capability_executor",
                error_type="invalid_calling_convention", latency_ms=(time.time() - start_time) * 1000)
        if calling_convention == "block":
            return self._dispatch_core_function(principal_id=principal_id, entry=entry, args=args,
                                                 request_id=request_id, start_time=start_time,
                                                 effective_permission_id=effective_permission_id,
                                                 grant_config=grant_config,
                                                 timeout_seconds=timeout_seconds)
        if calling_convention == "subprocess":
            entrypoint = entry.entrypoint or "main.py:run"
            function_dir = Path(entry.function_dir) if entry.function_dir else Path(".")
            ep_file = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else entrypoint
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=function_dir / ep_file, is_builtin=getattr(entry, "is_builtin", False))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time,
                                                     request_context=request_context)
        if calling_convention == "python_host":
            return self._execute_host_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        if calling_convention == "python_docker":
            return self._execute_user_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        if calling_convention == "binary":
            guard_resp = self._host_runtime_guard(entry, calling_convention, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_binary_function(principal_id=principal_id, entry=entry, args=args,
                                                  request_id=request_id, start_time=start_time)
        if calling_convention == "command":
            guard_resp = self._host_runtime_guard(entry, calling_convention, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_command_function(principal_id=principal_id, entry=entry, args=args,
                                                   request_id=request_id, start_time=start_time)
        return CapabilityResponse(success=False, error=f"Unknown calling_convention: {calling_convention}",
                                  error_type="invalid_calling_convention", latency_ms=(time.time() - start_time) * 1000)

    # ------------------------------------------------------------------
    # _dispatch_by_permission_id
    # ------------------------------------------------------------------

    def _dispatch_by_permission_id(self, entry, principal_id, effective_permission_id,
                                     grant_config, args, timeout_seconds, request_id, start_time):
        """calling_convention が None/未知の場合のフォールバック。"""
        if effective_permission_id == FLOW_RUN_PERMISSION_ID:
            return self._execute_flow_run(principal_id=principal_id, permission_id=effective_permission_id,
                                           grant_config=grant_config, args=args, timeout_seconds=timeout_seconds,
                                           request_id=request_id, start_time=start_time)
        elif effective_permission_id in DOCKER_PERMISSION_IDS:
            return self._execute_docker_dispatch(principal_id=principal_id, permission_id=effective_permission_id,
                                                  grant_config=grant_config, args=args,
                                                  request_id=request_id, start_time=start_time)
        else:
            entrypoint = entry.entrypoint or "main.py:run"
            function_dir = Path(entry.function_dir) if entry.function_dir else Path(".")
            ep_file = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else entrypoint
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=function_dir / ep_file, is_builtin=getattr(entry, "is_builtin", False))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time)

    # ------------------------------------------------------------------
    # function.call dispatch
    # ------------------------------------------------------------------

    def _execute_function_call(self, principal_id, request, start_time):
        """function.call リクエストを処理する。"""
        qualified_name = request.get("qualified_name")
        args = request.get("args", {})
        request_context = request.get("context") if isinstance(request.get("context"), dict) else None
        request_id = request.get("request_id", "")
        if not qualified_name or not isinstance(qualified_name, str):
            resp = CapabilityResponse(success=False, error="Missing or invalid qualified_name",
                                      error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason="Missing or invalid qualified_name")
            return resp
        if not self._initialized:
            self.initialize()
        if self._function_registry is None:
            resp = CapabilityResponse(success=False, error="FunctionRegistry is not available",
                                      error_type="function_registry_unavailable", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason="FunctionRegistry not available in DI container")
            return resp
        entry = self._function_registry.get(qualified_name)
        if entry is None and hasattr(self._function_registry, "resolve_by_alias"):
            try:
                alias_entry = self._function_registry.resolve_by_alias(qualified_name)
                if (
                    alias_entry is not None
                    and isinstance(getattr(alias_entry, "pack_id", None), str)
                    and isinstance(getattr(alias_entry, "function_id", None), str)
                ):
                    entry = alias_entry
            except Exception:
                logger.debug("Function alias lookup failed for '%s'", qualified_name, exc_info=True)
        if entry is None:
            resp = CapabilityResponse(success=False, error=f"Function not found: {qualified_name}",
                                      error_type="function_not_found", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason=f"Function '{qualified_name}' not found in FunctionRegistry")
            return resp
        pack_id = entry.pack_id
        is_core = pack_id.startswith(_CORE_PACK_ID_PREFIX)
        pack_root_hint = getattr(entry, "function_dir", None) or getattr(entry, "main_py_path", None)
        builtin_path_verdict = self._trusted_builtin_pack_path_verdict(pack_id, pack_root_hint)
        if builtin_path_verdict is None:
            is_trusted_builtin = self._is_trusted_builtin_pack(pack_id)
        else:
            is_trusted_builtin = builtin_path_verdict
        principal_is_trusted_builtin = self._is_trusted_builtin_pack(principal_id)
        if not principal_is_trusted_builtin and principal_id == pack_id:
            principal_is_trusted_builtin = is_trusted_builtin
        if pack_id in TRUSTED_BUILTIN_PACK_IDS and builtin_path_verdict is False:
            resp = CapabilityResponse(
                success=False,
                error=f"Built-in pack path is not trusted: {pack_id}",
                error_type="pack_not_approved",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(
                principal_id,
                "function.call",
                None,
                resp,
                args,
                request_id,
                detail_reason=f"Pack '{pack_id}' used a reserved built-in id from a non-canonical path",
            )
            return resp
        if self._approval_manager is not None:
            try:
                approved_result = self._approval_manager.is_pack_approved_and_verified(pack_id)
                if isinstance(approved_result, tuple):
                    is_approved, reason = approved_result
                else:
                    is_approved = bool(approved_result)
                    reason = None
                if not is_approved and self._dev_auto_reapprove_pack(pack_id):
                    approved_result = self._approval_manager.is_pack_approved_and_verified(pack_id)
                    if isinstance(approved_result, tuple):
                        is_approved, reason = approved_result
                    else:
                        is_approved = bool(approved_result)
                        reason = None
                if not is_approved:
                    resp = CapabilityResponse(success=False, error=f"Pack not approved: {pack_id}",
                                              error_type="pack_not_approved", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"Pack '{pack_id}' not approved: {reason}")
                    return resp
            except Exception as exc:
                if is_core:
                    logger.warning("approval_manager error during function.call for core pack '%s': %s (allowing execution for core pack)", pack_id, exc)
                else:
                    logger.error("approval_manager error during function.call for pack '%s': %s", pack_id, exc)
                    resp = CapabilityResponse(success=False, error="Approval verification failed",
                                              error_type="approval_check_error", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"approval_manager error for pack '{pack_id}': {exc}")
                    return resp
        if not (is_core or is_trusted_builtin) and entry.requires:
            for req_perm in entry.requires:
                if not self._has_permission_via_runtime_or_grant(pack_id, req_perm):
                    resp = CapabilityResponse(success=False,
                                              error=f"Function requires permission '{req_perm}' not granted to pack '{pack_id}'",
                                              error_type="requires_denied", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"Pack '{pack_id}' lacks required permission '{req_perm}'")
                    return resp
        if not principal_is_trusted_builtin:
            if not self._has_permission_via_runtime_or_grant(principal_id, "function.call"):
                resp = CapabilityResponse(success=False, error="Permission denied: function.call",
                                          error_type="permission_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, "function.call", None, resp, args, request_id,
                            detail_reason=f"Principal '{principal_id}' lacks 'function.call' permission")
                return resp
        if entry.caller_requires:
            caller_ok = False
            high_risk_approval_only = self._caller_requires_high_risk_approval_only(entry.caller_requires)
            if (
                not high_risk_approval_only
                and self._permission_manager is not None
                and hasattr(self._permission_manager, "check_caller_requires")
            ):
                caller_ok = self._permission_manager.check_caller_requires(principal_id, entry.caller_requires)
            if not caller_ok and self._request_context_satisfies_caller_requires(
                principal_id,
                entry.caller_requires,
                request_context,
                principal_is_trusted_builtin=principal_is_trusted_builtin,
            ):
                caller_ok = True
            if not caller_ok:
                resp = CapabilityResponse(success=False, error="Caller does not meet caller_requires",
                                          error_type="caller_requires_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, "function.call", None, resp, args, request_id,
                            detail_reason=f"Principal '{principal_id}' does not meet caller_requires: {entry.caller_requires}")
                return resp
        calling_convention = getattr(entry, "calling_convention", None)
        authorized, auth_resp, dispatch_grant_config = self._authorized_core_dispatch_config(
            principal_id, entry, start_time
        )
        if not authorized:
            self._audit(principal_id, "function.call", None, auth_resp, args, request_id,
                        detail_reason=f"Missing signed grant for core function '{entry.qualified_name}'")
            return auth_resp
        allow_manifest_calling_convention = is_core or is_trusted_builtin
        if (
            allow_manifest_calling_convention
            and calling_convention
            and calling_convention in _VALID_CALLING_CONVENTIONS
        ):
            resp = self._dispatch_by_calling_convention(
                calling_convention=calling_convention,
                entry=entry,
                principal_id=principal_id,
                effective_permission_id="function.call",
                grant_config=dispatch_grant_config,
                args=args,
                timeout_seconds=request.get("timeout_seconds", DEFAULT_FUNCTION_TIMEOUT),
                request_id=request_id,
                start_time=start_time,
                request_context=request_context,
            )
        elif is_core:
            resp = self._dispatch_core_function(principal_id=principal_id, entry=entry, args=args,
                                                 request_id=request_id, start_time=start_time,
                                                 effective_permission_id="function.call",
                                                 grant_config=dispatch_grant_config,
                                                 timeout_seconds=request.get("timeout_seconds", DEFAULT_FUNCTION_TIMEOUT))
        elif entry.host_execution:
            resp = self._execute_host_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        else:
            resp = self._execute_user_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        self._audit(principal_id, "function.call", None, resp, args, request_id,
                    extra_details={"qualified_name": qualified_name, "pack_id": pack_id, "is_core": is_core, "calling_convention": calling_convention})
        return resp

    def _request_context_satisfies_caller_requires(
        self,
        principal_id,
        caller_requires,
        request_context,
        *,
        principal_is_trusted_builtin=None,
    ):
        if principal_is_trusted_builtin is None:
            principal_is_trusted_builtin = self._is_trusted_builtin_pack(principal_id)
        if not principal_is_trusted_builtin:
            return False
        if not isinstance(request_context, dict):
            return False
        if request_context.get("_tool_server_approved") is not True:
            return False
        required = {str(item or "").strip() for item in caller_requires or []}
        return bool(required) and required <= {"user.approved.high_risk"}

    @staticmethod
    def _caller_requires_high_risk_approval_only(caller_requires):
        required = {str(item or "").strip() for item in caller_requires or []}
        return bool(required) and required <= {"user.approved.high_risk"}

    # ------------------------------------------------------------------
    # Docker / user function helpers
    # ------------------------------------------------------------------

    def _is_docker_available(self):
        return shutil.which("docker") is not None

    def _build_runner_payload(self, module_path, callable_name, context, args):
        return json.dumps(
            {
                "module_path": module_path,
                "callable_name": callable_name,
                "context": context,
                "args": args,
            },
            ensure_ascii=False,
            default=str,
        )

    def _runner_command(self):
        return [sys.executable, str(FUNCTION_RUNNER_PATH)]

    def _generate_function_runner_script(self):
        """Return the bundled runner script for legacy callers/tests."""
        return FUNCTION_RUNNER_PATH.read_text(encoding="utf-8")

    def _cleanup_temp_file(self, path, description):
        if not path:
            return
        try:
            os.unlink(path)
        except Exception:
            logger.debug("Failed to clean up %s: %s", description, path, exc_info=True)

    def _response_from_completed_process(self, proc, start_time, failure_prefix):
        latency_ms = (time.time() - start_time) * 1000
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            return CapabilityResponse(
                success=False,
                error=_sanitize_error(f"{failure_prefix}: {stderr}"[:1000]),
                error_type="function_execution_error",
                latency_ms=latency_ms,
            )
        stdout = proc.stdout or ""
        if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
            return CapabilityResponse(
                success=False,
                error="Response too large",
                error_type="response_too_large",
                latency_ms=latency_ms,
            )
        stdout_stripped = stdout.strip()
        if not stdout_stripped:
            return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
        try:
            return CapabilityResponse(
                success=True,
                output=json.loads(stdout_stripped),
                latency_ms=latency_ms,
            )
        except json.JSONDecodeError:
            return CapabilityResponse(
                success=False,
                error="Function output is not valid JSON",
                error_type="invalid_json_output",
                latency_ms=latency_ms,
            )

    def _run_runner_on_host(self, *, payload, cwd, timeout, start_time, failure_prefix):
        proc = subprocess.run(
            self._runner_command(),
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return self._response_from_completed_process(proc, start_time, failure_prefix)

    def _get_function_timeout(self, entry):
        grant_config = entry.manifest.get("grant_config", {}) if entry.manifest else {}
        t = grant_config.get("timeout", DEFAULT_FUNCTION_TIMEOUT)
        try:
            t = float(t)
        except (TypeError, ValueError):
            t = DEFAULT_FUNCTION_TIMEOUT
        return min(max(t, 1.0), MAX_TIMEOUT)

    def _host_runtime_guard(self, entry, runtime, start_time):
        if not getattr(entry, "host_execution", False):
            return CapabilityResponse(
                success=False,
                error=f"runtime='{runtime}' requires explicit host_execution approval",
                error_type="security_violation",
                latency_ms=(time.time() - start_time) * 1000,
            )
        allow_host = os.environ.get("RUMI_ALLOW_HOST_EXECUTION", "").lower()
        if allow_host not in ("1", "true"):
            return CapabilityResponse(
                success=False,
                error="Host execution is disabled. Set RUMI_ALLOW_HOST_EXECUTION=1 to enable.",
                error_type="host_execution_disabled",
                latency_ms=(time.time() - start_time) * 1000,
            )
        return None

    def _execute_user_function(self, principal_id, entry, args, request_id, start_time):
        runtime = getattr(entry, 'runtime', 'python')
        if runtime == "binary":
            guard_resp = self._host_runtime_guard(entry, runtime, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_binary_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time)
        elif runtime == "command":
            guard_resp = self._host_runtime_guard(entry, runtime, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_command_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time)
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        timeout = self._get_function_timeout(entry)
        if function_dir is None and main_py_path is None:
            return CapabilityResponse(success=False, error="User function execution is not configured", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        if self._is_docker_available() and _DockerRunBuilder is not None:
            return self._execute_user_function_docker(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout)
        else:
            logger.warning("Docker not available for user function %s:%s.", pack_id, function_id)
            security_mode = os.environ.get("RUMI_SECURITY_MODE", "").strip().lower()
            function_docker_policy = os.environ.get("RUMI_FUNCTION_DOCKER_POLICY", "").strip().lower()
            if security_mode == "strict" or function_docker_policy == "strict":
                return CapabilityResponse(success=False, error="Docker is not available and strict function isolation forbids host fallback.", error_type="docker_unavailable", latency_ms=(time.time() - start_time) * 1000)
            allow_fallback = os.environ.get("RUMI_ALLOW_HOST_FALLBACK", "").lower()
            if allow_fallback not in ("1", "true"):
                return CapabilityResponse(success=False, error="Docker is not available and host fallback is disabled. Set RUMI_ALLOW_HOST_FALLBACK=1 to enable.", error_type="docker_unavailable", latency_ms=(time.time() - start_time) * 1000)
            return self._execute_user_function_host(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout)

    def _execute_user_function_docker(self, principal_id, entry, args, request_id, start_time, timeout):
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir = Path(entry.function_dir)
        container_name = f"rumi-func-{pack_id}-{function_id}-{uuid.uuid4().hex[:8]}"
        runner_path = FUNCTION_RUNNER_PATH.resolve()
        context = {"principal_id": principal_id, "pack_id": pack_id, "function_id": function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = self._build_runner_payload("/function/main.py", "run", context, args)
        input_file = None
        try:
            fd, input_file = tempfile.mkstemp(suffix=".json", dir=_get_secure_tmp_dir())
            try:
                os.write(fd, input_json.encode("utf-8"))
            finally:
                os.close(fd)
            builder = _DockerRunBuilder(name=container_name)
            builder.volume(f"{function_dir.resolve()}:/function:ro")
            builder.volume(f"{input_file}:/input.json:ro")
            builder.volume(f"{runner_path}:/tmp/function_runner.py:ro")
            builder.env("RUMI_PACK_ID", pack_id); builder.env("RUMI_FUNCTION_ID", function_id)
            builder.label("rumi.managed", "true"); builder.label("rumi.type", "function"); builder.label("rumi.pack_id", pack_id)
            builder.image(getattr(entry, 'docker_image', '') or FUNCTION_BASE_IMAGE)
            builder.command(["python", "/tmp/function_runner.py", "--input-file", "/input.json"])
            proc = subprocess.run(builder.build(), capture_output=True, text=True, timeout=timeout)
            return self._response_from_completed_process(
                proc,
                start_time,
                f"Function execution failed (exit {proc.returncode})",
            )
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=5)
            except Exception:
                logger.debug("Failed to kill timed-out Docker function container '%s'", container_name, exc_info=True)
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            self._cleanup_temp_file(input_file, "Docker function input file")

    def _execute_user_function_host(self, principal_id, entry, args, request_id, start_time, timeout):
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = self._build_runner_payload(str(entry.main_py_path), "run", context, args)
        try:
            return self._run_runner_on_host(
                payload=input_json,
                cwd=str(Path(entry.function_dir)),
                timeout=timeout,
                start_time=start_time,
                failure_prefix="Function execution failed",
            )
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_host_function(self, principal_id, entry, args, request_id, start_time):
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        if function_dir is None and main_py_path is None:
            return CapabilityResponse(success=False, error="Host function execution is not configured", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        allow_host = os.environ.get("RUMI_ALLOW_HOST_EXECUTION", "").lower()
        if allow_host not in ("1", "true"):
            return CapabilityResponse(success=False, error="Host execution is disabled. Set RUMI_ALLOW_HOST_EXECUTION=1 to enable.", error_type="host_execution_disabled", latency_ms=(time.time() - start_time) * 1000)
        timeout = self._get_function_timeout(entry)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = self._build_runner_payload(str(main_py_path), "run", context, args)
        try:
            return self._run_runner_on_host(
                payload=input_json,
                cwd=str(Path(function_dir)),
                timeout=timeout,
                start_time=start_time,
                failure_prefix="Function execution failed",
            )
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _core_function_error_type(self, output, default="function_execution_error"):
        if isinstance(output, dict):
            return str(output.get("error_type") or output.get("code") or default)
        return default

    def _normalize_core_function_response(self, resp):
        if not resp.success:
            return resp
        output = resp.output
        if isinstance(output, dict) and (output.get("success") is False or output.get("status") == "error" or "error" in output):
            return CapabilityResponse(
                success=False,
                output=output,
                error=str(output.get("error") or output.get("message") or "Core function failed"),
                error_type=self._core_function_error_type(output),
                latency_ms=resp.latency_ms,
            )
        return resp

    def _execute_core_python_block(self, principal_id, entry, args, request_id, start_time,
                                   effective_permission_id, grant_config, timeout_seconds):
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        if function_dir is None:
            qualified_name = getattr(entry, "qualified_name", f"{entry.pack_id}:{entry.function_id}")
            return CapabilityResponse(
                success=False,
                error=f"Core function '{qualified_name}' has no function_dir",
                error_type="not_implemented",
                latency_ms=(time.time() - start_time) * 1000,
            )
        if main_py_path is None:
            main_py_path = Path(function_dir) / "main.py"
        if not Path(function_dir).is_dir():
            return CapabilityResponse(
                success=False,
                error=f"Core function_dir not found: {function_dir}",
                error_type="function_dir_not_found",
                latency_ms=(time.time() - start_time) * 1000,
            )
        if not Path(main_py_path).is_file():
            return CapabilityResponse(
                success=False,
                error=f"Core function entrypoint not found: {main_py_path}",
                error_type="not_implemented",
                latency_ms=(time.time() - start_time) * 1000,
            )
        timeout = min(max(float(timeout_seconds or DEFAULT_FUNCTION_TIMEOUT), 1.0), MAX_TIMEOUT)
        context = {
            "principal_id": principal_id,
            "pack_id": entry.pack_id,
            "function_id": entry.function_id,
            "permission_id": effective_permission_id,
            "grant_config": grant_config or {},
            "request_id": request_id,
            "ts": self._now_ts(),
        }
        input_json = self._build_runner_payload(str(main_py_path), "execute", context, args)
        try:
            resp = self._run_runner_on_host(
                payload=input_json,
                cwd=str(Path(function_dir)),
                timeout=timeout,
                start_time=start_time,
                failure_prefix="Core function execution failed",
            )
            return self._normalize_core_function_response(resp)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Core function execution timed out after {timeout}s",
                                      error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Core function execution error: {e}",
                                      error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _dispatch_core_function(self, principal_id, entry, args, request_id, start_time,
                                effective_permission_id=None, grant_config=None, timeout_seconds=None):
        pack_id, function_id = entry.pack_id, entry.function_id
        grant_config = dict(grant_config or {})
        permission_id = effective_permission_id or (entry.vocab_aliases[0] if getattr(entry, "vocab_aliases", None) else entry.qualified_name)
        if pack_id == "core_flow_capability" and function_id == "run":
            return self._execute_flow_run(principal_id=principal_id, permission_id=FLOW_RUN_PERMISSION_ID,
                                          grant_config=grant_config, args=args,
                                          timeout_seconds=timeout_seconds or DEFAULT_FUNCTION_TIMEOUT,
                                          request_id=request_id, start_time=start_time)
        di_service_name = self._core_function_handlers.get(pack_id)
        if di_service_name is None:
            if entry.main_py_path or entry.function_dir:
                if self._is_bundled_core_pack_entry(entry):
                    return self._execute_core_python_block(principal_id=principal_id, entry=entry, args=args,
                                                           request_id=request_id, start_time=start_time,
                                                           effective_permission_id=permission_id,
                                                           grant_config=grant_config,
                                                           timeout_seconds=timeout_seconds)
                logger.warning(
                    "Rejected unregistered core-prefixed function outside bundled core_pack: %s:%s",
                    pack_id,
                    function_id,
                )
            return CapabilityResponse(success=False, error=f"No handler registered for core pack: {pack_id}", error_type="unknown_core_function", latency_ms=(time.time() - start_time) * 1000)
        method_name = f"handle_{function_id}"
        try:
            from .di_container import get_container as _get_di
            handler = _get_di().get_or_none(di_service_name)
        except Exception:
            handler = None
        if handler is None:
            return CapabilityResponse(success=False, error=f"{di_service_name} is not available", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        try:
            result = getattr(handler, method_name)(principal_id=principal_id, args=args, grant_config=grant_config)
        except AttributeError:
            return CapabilityResponse(success=False, error=f"{di_service_name} has no method '{method_name}'", error_type="function_execution_error", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Core function failed: {e}", error_type="function_execution_error", latency_ms=(time.time() - start_time) * 1000)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(result, dict) and (result.get("success") is False or result.get("status") == "error" or "error" in result):
            return CapabilityResponse(success=False, output=result,
                                      error=str(result.get("error") or result.get("message") or "Core function failed"),
                                      error_type=self._core_function_error_type(result), latency_ms=latency_ms)
        return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)

    def _execute_binary_function(self, principal_id, entry, args, request_id, start_time):
        guard_resp = self._host_runtime_guard(entry, "binary", start_time)
        if guard_resp is not None:
            return guard_resp
        binary_path = entry.main_binary_path
        if binary_path is None or not Path(binary_path).is_file():
            return CapabilityResponse(success=False, error=f"Binary not found: {binary_path}", error_type="binary_not_found", latency_ms=(time.time() - start_time) * 1000)
        func_dir = Path(entry.function_dir).resolve()
        if not Path(binary_path).resolve().is_relative_to(func_dir):
            return CapabilityResponse(success=False, error="Binary path escapes function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        timeout = self._get_function_timeout(entry)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        try:
            proc = subprocess.run([str(binary_path)], input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=_sanitize_error(f"Binary exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}"), error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout: return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=json.loads(stdout), latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except json.JSONDecodeError:
            return CapabilityResponse(success=False, error="Output is not valid JSON", error_type="invalid_json_output", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_command_function(self, principal_id, entry, args, request_id, start_time):
        guard_resp = self._host_runtime_guard(entry, "command", start_time)
        if guard_resp is not None:
            return guard_resp
        command = getattr(entry, 'command', [])
        if not command or not isinstance(command, list):
            return CapabilityResponse(success=False, error="No command defined for runtime=command", error_type="invalid_config", latency_ms=(time.time() - start_time) * 1000)
        # Security: path traversal check (symmetric with _execute_binary_function).
        # The executable and, for interpreter commands, the script target must stay
        # inside the function directory.  Do not special-case sys.executable without
        # validating argv: python -c/-m or an out-of-tree script would otherwise let
        # pack-controlled command entries execute arbitrary host code.
        func_dir = Path(entry.function_dir).resolve() if entry.function_dir else None
        if func_dir:
            command_path = Path(command[0])
            if command_path.is_absolute():
                resolved_command_path = command_path.resolve()
                interpreter_path = Path(sys.executable).resolve()
                if resolved_command_path == interpreter_path:
                    if len(command) < 2 or str(command[1]).startswith("-"):
                        return CapabilityResponse(success=False, error="Python command must execute a script inside function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
                    script_path = Path(command[1])
                    if not script_path.is_absolute():
                        script_path = func_dir / script_path
                    if not script_path.resolve().is_relative_to(func_dir):
                        return CapabilityResponse(success=False, error="Python command script escapes function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
                elif not resolved_command_path.is_relative_to(func_dir):
                    return CapabilityResponse(success=False, error="Command path escapes function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        timeout = self._get_function_timeout(entry)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        func_dir = Path(entry.function_dir).resolve() if entry.function_dir else None
        try:
            proc = subprocess.run(command, input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir) if func_dir else None)
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=_sanitize_error(f"Command exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}"), error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout: return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=json.loads(stdout), latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except json.JSONDecodeError:
            return CapabilityResponse(success=False, error="Output is not valid JSON", error_type="invalid_json_output", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_flow_run(self, principal_id, permission_id, grant_config, args, timeout_seconds, request_id, start_time):
        flow_id = args.get("flow_id")
        if not flow_id or not isinstance(flow_id, str):
            return CapabilityResponse(success=False, error="Missing or invalid 'flow_id' in args", error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
        inputs = args.get("inputs") or {}
        if not isinstance(inputs, dict):
            return CapabilityResponse(success=False, error="'inputs' must be a dict", error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
        if self._kernel is None:
            return CapabilityResponse(success=False, error="Kernel not available for flow.run", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        if not hasattr(_flow_call_stack_local, "stack"): _flow_call_stack_local.stack = []
        call_stack = _flow_call_stack_local.stack
        if flow_id in call_stack:
            return CapabilityResponse(success=False, error=f"Recursive flow.run detected: {' -> '.join(call_stack + [flow_id])}", error_type="recursive_flow", latency_ms=(time.time() - start_time) * 1000)
        if len(call_stack) >= MAX_FLOW_CALL_DEPTH:
            return CapabilityResponse(success=False, error=f"Flow call depth limit exceeded ({MAX_FLOW_CALL_DEPTH}): {' -> '.join(call_stack + [flow_id])}", error_type="flow_depth_exceeded", latency_ms=(time.time() - start_time) * 1000)
        allowed_flow_ids = grant_config.get("allowed_flow_ids")
        if not isinstance(allowed_flow_ids, list):
            allowed_flow_ids = [allowed_flow_ids] if isinstance(allowed_flow_ids, str) else []
        if flow_id not in allowed_flow_ids:
            return CapabilityResponse(success=False, error="Permission denied", error_type="grant_denied", latency_ms=(time.time() - start_time) * 1000)
        remaining_timeout = max(min(float(args.get("timeout_seconds", timeout_seconds)), MAX_TIMEOUT) - (time.time() - start_time), 1.0)
        call_stack.append(flow_id)
        try:
            trusted_context = {
                "_flow_run_principal_id": principal_id,
                "_flow_run_request_id": request_id,
                "_flow_call_stack": list(call_stack),
            }
            context = sanitize_user_flow_context(inputs)
            result = self._kernel.execute_flow_sync(
                flow_id=flow_id,
                context=context,
                timeout=remaining_timeout,
                trusted_context=trusted_context,
            )
            latency_ms = (time.time() - start_time) * 1000
            if isinstance(result, dict) and result.get("_error"):
                return CapabilityResponse(success=False, error=result["_error"], error_type="flow_execution_error", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"flow.run execution failed: {e}", error_type="flow_execution_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            call_stack.pop()

    def _execute_docker_dispatch(self, principal_id, permission_id, grant_config, args, request_id, start_time):
        method_name = DOCKER_METHOD_MAP.get(permission_id)
        if method_name is None:
            return CapabilityResponse(success=False, error=f"Docker capability '{permission_id}' has no method mapping", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        return self._execute_docker_action(principal_id=principal_id, permission_id=permission_id, grant_config=grant_config, args=args, request_id=request_id, start_time=start_time, method_name=method_name)

    def _execute_docker_action(self, principal_id, permission_id, grant_config, args, request_id, start_time, method_name):
        try:
            from .di_container import get_container
            handler = get_container().get_or_none("docker_capability_handler")
        except Exception:
            handler = None
        if handler is None:
            return CapabilityResponse(success=False, error="DockerCapabilityHandler is not available", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        try:
            result = getattr(handler, method_name)(principal_id=principal_id, args=args, grant_config=grant_config)
        except AttributeError:
            return CapabilityResponse(success=False, error=f"DockerCapabilityHandler has no method '{method_name}'", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"{permission_id} execution failed: {e}", error_type="docker_execution_error", latency_ms=(time.time() - start_time) * 1000)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(result, dict) and "error" in result:
            return CapabilityResponse(success=False, output=result, error=result["error"], error_type=f"{permission_id.replace('.', '_')}_error", latency_ms=latency_ms)
        return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)

    def _execute_handler_subprocess(self, handler_def, principal_id, permission_id, grant_config, args, timeout_seconds, request_id, start_time, request_context=None):
        ep_file, ep_func = handler_def.entrypoint.rsplit(":", 1)
        handler_py_path = handler_def.handler_dir / ep_file
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "permission_id": permission_id, "handler_id": handler_def.handler_id, "grant_config": grant_config, "request_id": request_id, "ts": self._now_ts()})
        input_json = self._build_runner_payload(str(handler_py_path), ep_func, context, args)
        try:
            return self._run_runner_on_host(
                payload=input_json,
                cwd=str(Path(__file__).parent.parent) if getattr(handler_def, "is_builtin", False) else str(handler_def.handler_dir),
                timeout=timeout_seconds,
                start_time=start_time,
                failure_prefix="Handler execution failed",
            )
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error="Handler execution timed out", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception:
            logger.debug("Handler subprocess execution failed", exc_info=True)
            return CapabilityResponse(success=False, error="Internal execution error", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _check_rate_limit(self, principal_id):
        try:
            return self._rate_limit_store.allow(
                principal_id=principal_id,
                scope=SECRET_GET_PERMISSION_ID,
                limit=self._secret_get_rate_limit,
                window_seconds=60.0,
            )
        except Exception:
            logger.debug("Persistent rate limit check failed for '%s'", principal_id, exc_info=True)
            return False

    def _audit(self, principal_id, permission_id, handler_id, response, args, request_id,
               trusted=None, grant_allowed=None, grant_reason=None, detail_reason=None, extra_details=None):
        try:
            audit = get_audit_logger()
            details = {"principal_id": principal_id, "permission_id": permission_id, "handler_id": handler_id,
                        "request_id": request_id, "latency_ms": response.latency_ms, "args_summary": _summarize_args(args)}
            if trusted is not None: details["trusted"] = trusted
            if grant_allowed is not None: details["grant_allowed"] = grant_allowed
            if grant_reason is not None: details["grant_reason"] = grant_reason
            if detail_reason is not None: details["detail_reason"] = detail_reason
            if extra_details: details.update(extra_details)
            if response.error: details["error"] = response.error; details["error_type"] = response.error_type
            rejection_reason = str(detail_reason or grant_reason or response.error or "")
            audit.log_permission_event(pack_id=principal_id, permission_type="capability", action="execute",
                                        success=response.success, details=details,
                                        rejection_reason=rejection_reason if not response.success else "")
        except Exception:
            logger.debug("Capability audit logging failed", exc_info=True)


_global_executor: Optional[CapabilityExecutor] = None
_executor_lock = threading.Lock()

def get_capability_executor() -> CapabilityExecutor:
    from .di_container import get_container
    executor = get_container().get("capability_executor")
    if not getattr(executor, "_initialized", False):
        executor.initialize()
    return executor

def reset_capability_executor() -> CapabilityExecutor:
    global _global_executor
    from .di_container import get_container
    container = get_container()
    new = CapabilityExecutor()
    new.initialize()
    with _executor_lock:
        _global_executor = new
    container.set_instance("capability_executor", new)
    return new
