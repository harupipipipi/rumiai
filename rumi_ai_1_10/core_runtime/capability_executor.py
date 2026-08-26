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

import hashlib
import json
import logging
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import types
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from .execution_boundary import (
    ExecutionBoundary,
    SANDBOX_RUNTIME_UNAVAILABLE,
    profile_runtime_name,
)
from .flow_context_security import sanitize_user_flow_context
from .pack_function_policy import permission_id_for_entry
from .rate_limit_store import PersistentRateLimitStore

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
# Keep the short and package-qualified import names aliased so order-dependent
# tests do not see two copies of the same helper module.
from . import crypto_utils as _loaded_crypto_utils
from .crypto_utils import compute_file_sha256 as _imported_compute_file_sha256

_crypto_utils = (
    sys.modules.get("rumi_ai_1_10.core_runtime.crypto_utils")
    or sys.modules.get("core_runtime.crypto_utils")
    or _loaded_crypto_utils
)
sys.modules["core_runtime.crypto_utils"] = _crypto_utils
sys.modules["rumi_ai_1_10.core_runtime.crypto_utils"] = _crypto_utils
# def compute_file_sha256 is provided by crypto_utils and re-exported here.
compute_file_sha256 = getattr(_crypto_utils, "compute_file_sha256", _imported_compute_file_sha256)

_this_module = sys.modules.get(__name__)
if _this_module is not None:
    if __name__.startswith("rumi_ai_1_10."):
        sys.modules.setdefault(__name__.removeprefix("rumi_ai_1_10."), _this_module)
    else:
        sys.modules.setdefault(f"rumi_ai_1_10.{__name__}", _this_module)

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
MAX_HOST_ARGS_SUMMARY_VALUE_LENGTH = 160
MAX_HOST_ARGS_SUMMARY_ITEMS = 6
_HOST_ARG_SECRET_TOKENS = {
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "env",
    "environment",
    "key",
    "passwd",
    "password",
    "private",
    "pwd",
    "secret",
    "stdin",
    "token",
}
_HOST_ARG_TARGET_TOKENS = {
    "cwd",
    "directory",
    "dir",
    "endpoint",
    "file",
    "files",
    "path",
    "paths",
    "target",
    "targets",
    "uri",
    "url",
    "urls",
    "working",
}
_HOST_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_HOST_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

logger = logging.getLogger(__name__)
FUNCTION_RUNNER_PATH = Path(__file__).with_name("function_runner.py")
TRUSTED_BUILTIN_PACK_IDS = {
    "defaultspack",
    "rumi_default_tools_pack",
    "rumi_host_capabilities_pack",
    "rumi_workspace_surfaces",
}

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
    pack_id: str = ""



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


def _secure_tmp_state_module():
    """Return the module object that carries test monkeypatches for temp paths."""
    current = sys.modules.get(__name__)
    for module_name in (
        "core_runtime.capability_executor",
        "rumi_ai_1_10.core_runtime.capability_executor",
    ):
        candidate = sys.modules.get(module_name)
        if candidate is None:
            continue
        if getattr(candidate, "__file__", None) != globals().get("__file__"):
            return candidate
    return current


def _get_secure_tmp_dir() -> str:
    """user_data/tmp/ 配下に安全な一時ディレクトリを返す（パーミッション 0700）。

    ディレクトリが存在しない場合は作成する。
    """
    global _SECURE_TMP_DIR
    state_module = _secure_tmp_state_module()
    cached_dir = getattr(state_module, "_SECURE_TMP_DIR", _SECURE_TMP_DIR)
    if cached_dir is not None and Path(cached_dir).is_dir():
        return str(cached_dir)
    with _secure_tmp_lock:
        cached_dir = getattr(state_module, "_SECURE_TMP_DIR", _SECURE_TMP_DIR)
        if cached_dir is not None and Path(cached_dir).is_dir():
            return str(cached_dir)
        module_file = getattr(state_module, "__file__", __file__)
        base = Path(module_file).resolve().parent.parent / "user_data" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(str(base), 0o700)
        _SECURE_TMP_DIR = base
        if state_module is not None:
            setattr(state_module, "_SECURE_TMP_DIR", base)
        return str(_SECURE_TMP_DIR)


def _arg_key_tokens(key: Any) -> list[str]:
    raw = str(key or "")
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    return [token for token in re.split(r"[^a-z0-9]+", spaced.lower()) if token]


def _is_sensitive_arg_key(key: Any) -> bool:
    tokens = _arg_key_tokens(key)
    joined = "_".join(tokens)
    if "api_key" in joined or "private_key" in joined:
        return True
    return any(token in _HOST_ARG_SECRET_TOKENS for token in tokens)


def _is_target_arg_key(key: Any) -> bool:
    tokens = _arg_key_tokens(key)
    joined = "_".join(tokens)
    if joined in {"working_dir", "working_directory"}:
        return True
    return any(token in _HOST_ARG_TARGET_TOKENS for token in tokens)


def _safe_host_summary_text(value: Any, max_length: int = MAX_HOST_ARGS_SUMMARY_VALUE_LENGTH) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_length:
        return text[:max(0, max_length - 14)] + "...(truncated)"
    return text


def _sanitize_host_url(value: Any) -> str:
    text = _safe_host_summary_text(value)
    match = re.match(r"^(https?://\S+)", text, re.IGNORECASE)
    if not match:
        return ""
    try:
        parsed = urlsplit(match.group(1))
    except ValueError:
        return ""
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return ""
    hostname = parsed.hostname or ""
    if not hostname:
        return ""
    if ":" in hostname and not (hostname.startswith("[") and hostname.endswith("]")):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return _safe_host_summary_text(urlunsplit((scheme, netloc, parsed.path or "", "", "")))


def _looks_like_host_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or _HOST_URL_RE.match(text):
        return False
    return (
        text.startswith(("/", "./", "../", "~/", "\\\\"))
        or bool(_HOST_WINDOWS_PATH_RE.match(text))
    )


def _append_limited_unique(target: list[str], value: str) -> None:
    if value and value not in target and len(target) < MAX_HOST_ARGS_SUMMARY_ITEMS:
        target.append(value)


def _split_flag_value(token: Any) -> str:
    text = str(token or "").strip()
    if text.startswith("-") and "=" in text:
        return text.split("=", 1)[1]
    return text


def _collect_host_targets(value: Any, *, paths: list[str], urls: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _is_sensitive_arg_key(key):
                continue
            if _is_target_arg_key(key):
                _collect_host_targets(nested, paths=paths, urls=urls)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_host_targets(item, paths=paths, urls=urls)
        return
    text = _split_flag_value(value)
    url = _sanitize_host_url(text)
    if url:
        _append_limited_unique(urls, url)
        return
    if _looks_like_host_path(text):
        _append_limited_unique(paths, _safe_host_summary_text(text))


def _host_command_tokens(args: dict[str, Any]) -> list[str]:
    raw_argv = args.get("argv")
    if isinstance(raw_argv, (list, tuple)):
        return [_safe_host_summary_text(item) for item in raw_argv if str(item or "").strip()]
    raw_args = args.get("args")
    if isinstance(raw_args, (list, tuple)):
        return [_safe_host_summary_text(item) for item in raw_args if str(item or "").strip()]
    for key in ("executable", "binary", "program"):
        value = args.get(key)
        if value is not None:
            return [_safe_host_summary_text(value)]
    for key in ("command", "cmd"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return _tokenize_host_command_text(value)
    return []


def _tokenize_host_command_text(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    return [_safe_host_summary_text(part) for part in parts if str(part or "").strip()]


def _collect_host_targets_from_command_tokens(tokens: list[str], *, paths: list[str], urls: list[str]) -> None:
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if _is_sensitive_cli_token(token):
            skip_next = "=" not in str(token or "")
            continue
        _collect_host_targets(token, paths=paths, urls=urls)


def _is_sensitive_cli_token(value: Any) -> bool:
    text = str(value or "").strip().lower().lstrip("-/")
    if not text:
        return False
    token_name = re.split(r"[=\s:]", text, maxsplit=1)[0]
    return _is_sensitive_arg_key(token_name)


def _redact_sensitive_args(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        redacted_count = 0
        for key, nested in value.items():
            if _is_sensitive_arg_key(key):
                redacted_count += 1
                continue
            if str(key).strip().lower() in {"command", "cmd"} and isinstance(nested, str):
                redacted[str(key)] = _redact_host_command_text(nested)
                continue
            redacted[str(key)] = _redact_sensitive_args(nested)
        if redacted_count:
            redacted["_redacted_field_count"] = redacted_count
        return redacted
    if isinstance(value, (list, tuple)):
        redacted_items: list[Any] = []
        skip_next = False
        for item in value:
            if skip_next:
                redacted_items.append("[redacted]")
                skip_next = False
                continue
            if isinstance(item, str) and _is_sensitive_cli_token(item):
                redacted_items.append("[redacted]")
                skip_next = "=" not in item
                continue
            redacted_items.append(_redact_sensitive_args(item))
        return redacted_items
    if isinstance(value, str) and _HOST_URL_RE.match(value.strip()):
        return _sanitize_host_url(value)
    return value


def _redact_host_command_text(value: str) -> list[Any]:
    redacted_items: list[Any] = []
    skip_next = False
    for item in _tokenize_host_command_text(value):
        if skip_next:
            redacted_items.append("[redacted]")
            skip_next = False
            continue
        if _is_sensitive_cli_token(item):
            redacted_items.append("[redacted]")
            skip_next = "=" not in item
            continue
        redacted_items.append(_redact_sensitive_args(item))
    return redacted_items


def _summarize_args(args: Any, max_length: int = MAX_ARGS_SUMMARY_LENGTH) -> str:
    """args を監査ログ用に要約"""
    try:
        s = json.dumps(_redact_sensitive_args(args), ensure_ascii=False, default=str)
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
                if self._looks_like_function_entry(entry):
                    return entry
            entry = fr.resolve_by_alias(permission_id)
            if self._looks_like_function_entry(entry):
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

    @staticmethod
    def _looks_like_function_entry(entry) -> bool:
        return entry is not None and isinstance(getattr(entry, "qualified_name", None), str)

    def _coerce_legacy_entry(self, candidate, permission_id: str):
        """旧 handler registry の定義を FunctionEntry 互換の最小 shape に寄せる。"""
        if candidate is None:
            return None
        handler_id = getattr(candidate, "handler_id", None)
        entrypoint = getattr(candidate, "entrypoint", None)
        if not isinstance(handler_id, str):
            return None
        if entrypoint is not None and not isinstance(entrypoint, str):
            return None
        handler_dir = getattr(candidate, "handler_dir", None) or Path(".")
        handler_py_path = getattr(candidate, "handler_py_path", None)
        is_builtin = bool(getattr(candidate, "is_builtin", False))
        pack_id = getattr(candidate, "pack_id", None)
        if not isinstance(pack_id, str):
            pack_id = None
        if not pack_id:
            pack_id = f"{_CORE_PACK_ID_PREFIX}legacy" if is_builtin else "legacy_pack"
        main_py_path = getattr(candidate, "main_py_path", None)
        if not isinstance(main_py_path, (str, Path)):
            main_py_path = handler_py_path
        grant_config = getattr(candidate, "grant_config", None)
        if not isinstance(grant_config, dict):
            grant_config = None
        qualified_name = getattr(candidate, "qualified_name", None)
        if not isinstance(qualified_name, str):
            qualified_name = handler_id
        calling_convention = getattr(candidate, "calling_convention", None)
        if not isinstance(calling_convention, str):
            calling_convention = None
        function_dir = getattr(candidate, "function_dir", None)
        if not isinstance(function_dir, (str, Path)):
            function_dir = handler_dir
        vocab_aliases = getattr(candidate, "vocab_aliases", None)
        if not isinstance(vocab_aliases, list):
            vocab_aliases = [permission_id]
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
            legacy_grant_required=True,
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
    def _entry_requires_trust(entry) -> bool:
        manifest = getattr(entry, "manifest", None)
        if not isinstance(manifest, dict):
            manifest = {}
        calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
        return bool(
            getattr(entry, "handler_py_sha256", None)
            or (
                getattr(entry, "main_py_path", None) is not None
                and calling_convention not in {"binary", "command"}
            )
            or calling_convention in {"python_host", "binary", "command"}
            or bool(manifest.get("trust_required"))
        )

    @staticmethod
    def _entry_trust_path(entry) -> Path | None:
        calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
        if calling_convention == "binary":
            binary_path = getattr(entry, "main_binary_path", None)
            return Path(binary_path) if binary_path else None
        if calling_convention == "command":
            command = getattr(entry, "command", None) or []
            if command and isinstance(command[0], str) and command[0]:
                command_path = Path(command[0])
                if not command_path.is_absolute():
                    raise PermissionError(
                        "Command entrypoints must use an absolute executable path"
                    )
                return command_path
            return None

        main_py_path = getattr(entry, "main_py_path", None)
        if main_py_path:
            return Path(main_py_path)

        function_dir = getattr(entry, "function_dir", None)
        entrypoint = getattr(entry, "entrypoint", None) or "main.py:run"
        entrypoint_file = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else entrypoint
        if function_dir:
            return Path(function_dir) / entrypoint_file
        return None

    def _check_entry_trust(self, entry, permission_id: str) -> str | None:
        if not self._entry_requires_trust(entry):
            return None
        try:
            trust_path = self._entry_trust_path(entry)
        except PermissionError as exc:
            return str(exc)
        if trust_path is None:
            return "Executable path not available for trust verification"
        try:
            resolved_path = trust_path.resolve()
        except OSError:
            resolved_path = trust_path
        if not resolved_path.is_file():
            return "Executable path not found for trust verification"
        if self._trust_store is None:
            return "Trust store unavailable for execution-time verification"
        try:
            actual_sha256 = compute_file_sha256(resolved_path)
        except Exception:
            return "Failed to compute handler sha256 at execution time"
        qualified_name = getattr(entry, "qualified_name", None)
        trust_id = qualified_name.strip() if isinstance(qualified_name, str) and qualified_name.strip() else permission_id
        trust_result = self._trust_store.is_trusted(trust_id, actual_sha256)
        if trust_result.trusted:
            return None
        return trust_result.reason

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

    def _core_pack_dir_candidates(self) -> List[Any]:
        candidates: List[Any] = [_CORE_PACK_DIR]
        current_module = sys.modules.get(__name__)
        for module_name in (
            "core_runtime.capability_executor",
            "rumi_ai_1_10.core_runtime.capability_executor",
        ):
            module = sys.modules.get(module_name)
            if module is None or module is current_module:
                continue
            candidate = getattr(module, "_CORE_PACK_DIR", None)
            if candidate is not None and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def _is_bundled_core_pack_entry(self, entry) -> bool:
        """Return True only for entries shipped from core_runtime/core_pack/<pack_id>."""
        pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        if not pack_id.startswith(_CORE_PACK_ID_PREFIX):
            return False

        entry_paths = [
            getattr(entry, "function_dir", None),
            getattr(entry, "main_py_path", None),
        ]
        for raw_core_pack_dir in self._core_pack_dir_candidates():
            try:
                core_pack_root = Path(raw_core_pack_dir).resolve()
            except (OSError, TypeError):
                try:
                    core_pack_root = Path(raw_core_pack_dir)
                except TypeError:
                    continue
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
        return False

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
                verdict = helper(normalized_pack_id)
                if isinstance(verdict, bool):
                    return verdict
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

        pack_id = str(getattr(entry, "pack_id", "") or "")
        pack_root_hint = getattr(entry, "function_dir", None) or getattr(entry, "main_py_path", None)
        is_trusted_builtin = self._is_trusted_builtin_pack(pack_id, pack_root_hint=pack_root_hint)
        is_core_builtin = self._is_core_builtin_trust_bypass_entry(entry)
        if self._approval_manager is not None and not (is_core_builtin or is_trusted_builtin):
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
                    resp = CapabilityResponse(
                        success=False,
                        error=f"Pack not approved: {pack_id}",
                        error_type="pack_not_approved",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                    self._audit(
                        principal_id,
                        effective_permission_id,
                        handler_id,
                        resp,
                        args,
                        request_id,
                        detail_reason=f"Pack '{pack_id}' not approved: {reason}",
                    )
                    return resp
            except Exception as exc:
                if is_core_builtin or is_trusted_builtin:
                    logger.warning("approval_manager error during permission_id execute for built-in pack '%s': %s (allowing execution for built-in pack)", pack_id, exc)
                else:
                    logger.error("approval_manager error during permission_id execute for pack '%s': %s", pack_id, exc)
                    resp = CapabilityResponse(
                        success=False,
                        error="Approval verification failed",
                        error_type="approval_check_error",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                    self._audit(
                        principal_id,
                        effective_permission_id,
                        handler_id,
                        resp,
                        args,
                        request_id,
                        detail_reason=f"approval_manager error for pack '{pack_id}': {exc}",
                    )
                    return resp

        # 2. Trust チェック
        # Only core entries loaded from the bundled core_pack tree may bypass the
        # normal trust-store check.  A pack_id prefix alone is attacker-controlled
        # metadata for imported ecosystem packs.
        is_builtin = self._is_core_builtin_trust_bypass_entry(entry)
        builtin_sha256 = None

        if is_builtin:
            trust_path = self._entry_trust_path(entry)
            if trust_path is not None and Path(trust_path).is_file():
                try:
                    builtin_sha256 = compute_file_sha256(Path(trust_path))
                except Exception:
                    builtin_sha256 = "compute_failed"
        else:
            trust_permission_id = (
                getattr(entry, "permission_id", None)
                or getattr(entry, "qualified_name", handler_id)
            )
            trust_error = self._check_entry_trust(entry, trust_permission_id)
            if trust_error:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason=trust_error)
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
                self._log_caller_requires_denied(
                    principal_id=principal_id,
                    caller_requires=caller_requires,
                    request_context=request_context,
                    principal_is_trusted_builtin=principal_is_trusted_builtin,
                    caller_ok=caller_ok,
                    permission_id=effective_permission_id,
                    handler_id=handler_id,
                    entry=entry,
                )
                resp = CapabilityResponse(success=False, error="Caller does not meet caller_requires",
                                          error_type="caller_requires_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=True, detail_reason=f"Principal '{principal_id}' does not meet caller_requires: {caller_requires}")
                return resp

        # 4. Grant チェック（host/binary/command は manifest grant_config がなくても必須）
        calling_convention = getattr(entry, "calling_convention", None)
        entry_grant_config = self._entry_grant_config(entry)
        host_grant_required = calling_convention in {
            "python_host",
            "binary",
            "command",
        }
        # Unified FunctionRegistry execution preserves the legacy capability
        # boundary: every principal x permission dispatch requires a grant.
        grant_required = True
        grant_config = dict(entry_grant_config or {})
        if grant_required:
            if self._grant_manager is None:
                resp = CapabilityResponse(
                    success=False,
                    error="Capability grant manager is not available",
                    error_type="grant_manager_unavailable",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id,
                    effective_permission_id,
                    handler_id,
                    resp,
                    args,
                    request_id,
                    trusted=True,
                    grant_allowed=False,
                    grant_reason="CapabilityGrantManager not available",
                )
                return resp
            grant_permission_id = (
                permission_id_for_entry(entry)
                if isinstance(getattr(entry, "permission_id", None), str)
                else effective_permission_id
            )
            if host_grant_required:
                grant_result = self._grant_manager.check(pack_id, grant_permission_id)
                if not grant_result.allowed and principal_id != pack_id:
                    caller_grant_result = self._grant_manager.check(principal_id, grant_permission_id)
                    if caller_grant_result.allowed:
                        grant_result = caller_grant_result
            else:
                grant_result = self._grant_manager.check(principal_id, grant_permission_id)
            if not grant_result.allowed:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="grant_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=True, grant_allowed=False, grant_reason=grant_result.reason)
                return resp
            result_config = getattr(grant_result, "config", None)
            if isinstance(result_config, dict):
                grant_config.update(result_config)

        host_boundary_resp = self._host_boundary_response_if_needed(
            entry=entry,
            principal_id=principal_id,
            request_id=request_id,
            start_time=start_time,
            request_context=request_context,
            args=args,
        )
        if host_boundary_resp is not None:
            self._audit(
                principal_id,
                effective_permission_id,
                handler_id,
                host_boundary_resp,
                args,
                request_id,
                trusted=True,
                detail_reason="Direct host access requires critical typed confirmation",
            )
            return host_boundary_resp

        # 5. calling_convention 分岐
        if calling_convention and calling_convention in _VALID_CALLING_CONVENTIONS:
            resp = self._dispatch_by_calling_convention(
                calling_convention=calling_convention, entry=entry, principal_id=principal_id,
                effective_permission_id=effective_permission_id, grant_config=grant_config,
                args=args, timeout_seconds=timeout_seconds, request_id=request_id, start_time=start_time,
                request_context=request_context)
        else:
            resp = self._dispatch_by_permission_id(
                entry=entry, principal_id=principal_id, effective_permission_id=effective_permission_id,
                grant_config=grant_config, args=args, timeout_seconds=timeout_seconds,
                request_id=request_id, start_time=start_time, request_context=request_context)

        resp = self._response_after_host_intent_handling(
            resp,
            entry=entry,
            principal_id=principal_id,
            request_context=request_context,
            start_time=start_time,
        )

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
            trusted_handler_path = Path(entry.main_py_path) if getattr(entry, "main_py_path", None) else function_dir / ep_file
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=trusted_handler_path,
                                          is_builtin=(
                                              getattr(entry, "is_builtin", False) is True
                                              or self._is_core_builtin_trust_bypass_entry(entry)
                                          ),
                                          pack_id=str(getattr(entry, "pack_id", "") or ""))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time,
                                                     request_context=request_context)
        if calling_convention == "python_host":
            return self._execute_host_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=grant_config,
                request_context=request_context,
                timeout_seconds=timeout_seconds,
            )
        if calling_convention == "python_docker":
            return self._execute_user_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=grant_config,
                request_context=request_context,
                force_docker=True,
                timeout_seconds=timeout_seconds,
            )
        if calling_convention == "binary":
            guard_resp = self._host_runtime_guard(entry, calling_convention, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_binary_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=grant_config,
                request_context=request_context,
                timeout_seconds=timeout_seconds,
            )
        if calling_convention == "command":
            guard_resp = self._host_runtime_guard(entry, calling_convention, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_command_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=grant_config,
                request_context=request_context,
                timeout_seconds=timeout_seconds,
            )
        return CapabilityResponse(success=False, error=f"Unknown calling_convention: {calling_convention}",
                                  error_type="invalid_calling_convention", latency_ms=(time.time() - start_time) * 1000)

    # ------------------------------------------------------------------
    # _dispatch_by_permission_id
    # ------------------------------------------------------------------

    def _dispatch_by_permission_id(self, entry, principal_id, effective_permission_id,
                                     grant_config, args, timeout_seconds, request_id, start_time,
                                     request_context=None):
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
            trusted_handler_path = Path(entry.main_py_path) if getattr(entry, "main_py_path", None) else function_dir / ep_file
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=trusted_handler_path,
                                          is_builtin=(
                                              getattr(entry, "is_builtin", False) is True
                                              or self._is_core_builtin_trust_bypass_entry(entry)
                                          ),
                                          pack_id=str(getattr(entry, "pack_id", "") or ""))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time,
                                                     request_context=request_context)

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
        elif builtin_path_verdict is False:
            is_trusted_builtin = self._is_trusted_builtin_pack(pack_id)
        else:
            is_trusted_builtin = builtin_path_verdict
        is_core_builtin = self._is_core_builtin_trust_bypass_entry(entry)
        principal_is_trusted_builtin = self._is_trusted_builtin_pack(principal_id)
        if is_core and not is_core_builtin and not is_trusted_builtin:
            resp = CapabilityResponse(
                success=False,
                error=f"No handler registered for core pack: {pack_id}",
                error_type="unknown_core_function",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(
                principal_id,
                "function.call",
                None,
                resp,
                args,
                request_id,
                detail_reason=f"Rejected reserved core-prefixed function outside bundled core_pack: {qualified_name}",
            )
            return resp
        if not principal_is_trusted_builtin and principal_id == pack_id:
            principal_is_trusted_builtin = is_trusted_builtin
        if (
            not principal_is_trusted_builtin
            and is_trusted_builtin
            and principal_id in TRUSTED_BUILTIN_PACK_IDS
        ):
            principal_is_trusted_builtin = True
        if (
            pack_id in TRUSTED_BUILTIN_PACK_IDS
            and builtin_path_verdict is False
            and principal_id == pack_id
            and not is_trusted_builtin
        ):
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
        if self._approval_manager is not None and not (is_core_builtin or is_trusted_builtin):
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
                if is_core_builtin or is_trusted_builtin:
                    logger.warning("approval_manager error during function.call for core pack '%s': %s (allowing execution for core pack)", pack_id, exc)
                else:
                    logger.error("approval_manager error during function.call for pack '%s': %s", pack_id, exc)
                    resp = CapabilityResponse(success=False, error="Approval verification failed",
                                              error_type="approval_check_error", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"approval_manager error for pack '{pack_id}': {exc}")
                    return resp
        if not (is_core_builtin or is_trusted_builtin):
            trust_error = self._check_entry_trust(entry, permission_id_for_entry(entry))
            if trust_error:
                resp = CapabilityResponse(
                    success=False,
                    error="Permission denied",
                    error_type="trust_denied",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id,
                    "function.call",
                    None,
                    resp,
                    args,
                    request_id,
                    detail_reason=f"Function trust denied for '{qualified_name}': {trust_error}",
                )
                return resp
        if not (is_core_builtin or is_trusted_builtin) and entry.requires:
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
                self._log_caller_requires_denied(
                    principal_id=principal_id,
                    caller_requires=entry.caller_requires,
                    request_context=request_context,
                    principal_is_trusted_builtin=principal_is_trusted_builtin,
                    caller_ok=caller_ok,
                    permission_id="function.call",
                    handler_id=str(getattr(entry, "qualified_name", "") or ""),
                    entry=entry,
                )
                resp = CapabilityResponse(success=False, error="Caller does not meet caller_requires",
                                          error_type="caller_requires_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, "function.call", None, resp, args, request_id,
                            detail_reason=f"Principal '{principal_id}' does not meet caller_requires: {entry.caller_requires}")
                return resp
        host_boundary_resp = self._host_boundary_response_if_needed(
            entry=entry,
            principal_id=principal_id,
            request_id=request_id,
            start_time=start_time,
            request_context=request_context,
            args=args,
        )
        if host_boundary_resp is not None:
            self._audit(
                principal_id,
                "function.call",
                None,
                host_boundary_resp,
                args,
                request_id,
                detail_reason="Direct host access requires critical typed confirmation",
            )
            return host_boundary_resp
        calling_convention = getattr(entry, "calling_convention", None)
        authorized, auth_resp, dispatch_grant_config = self._authorized_core_dispatch_config(
            principal_id, entry, start_time
        )
        if not authorized:
            self._audit(principal_id, "function.call", None, auth_resp, args, request_id,
                        detail_reason=f"Missing signed grant for core function '{entry.qualified_name}'")
            return auth_resp
        entry_grant_config = self._entry_grant_config(entry)
        host_grant_required = calling_convention in {"python_host", "binary", "command"}
        grant_required = (
            not is_core_builtin
            and (entry_grant_config is not None or host_grant_required)
        )
        if not is_core_builtin:
            dispatch_grant_config.update(dict(entry_grant_config or {}))
        if grant_required:
            if self._grant_manager is None:
                resp = CapabilityResponse(
                    success=False,
                    error="Capability grant manager is not available",
                    error_type="grant_manager_unavailable",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id,
                    "function.call",
                    None,
                    resp,
                    args,
                    request_id,
                    detail_reason="CapabilityGrantManager not available",
                )
                return resp
            permission_id = permission_id_for_entry(entry)
            grant_result = self._grant_manager.check(pack_id, permission_id)
            if not grant_result.allowed and principal_id != pack_id:
                caller_grant_result = self._grant_manager.check(principal_id, permission_id)
                if caller_grant_result.allowed:
                    grant_result = caller_grant_result
            if not grant_result.allowed:
                resp = CapabilityResponse(
                    success=False,
                    error="Permission denied",
                    error_type="grant_denied",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id,
                    "function.call",
                    None,
                    resp,
                    args,
                    request_id,
                    detail_reason=(
                        f"Neither pack '{pack_id}' nor principal '{principal_id}' "
                        f"has grant for '{permission_id}': {grant_result.reason}"
                    ),
                )
                return resp
            result_config = getattr(grant_result, "config", None)
            if isinstance(result_config, dict):
                dispatch_grant_config.update(result_config)
        allow_manifest_calling_convention = is_core_builtin or is_trusted_builtin
        if is_core_builtin and not (
            is_trusted_builtin
            or self._is_bundled_core_pack_entry(entry)
            or pack_id in self._core_function_handlers
        ):
            allow_manifest_calling_convention = False
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
        elif is_core_builtin:
            resp = self._dispatch_core_function(principal_id=principal_id, entry=entry, args=args,
                                                 request_id=request_id, start_time=start_time,
                                                 effective_permission_id="function.call",
                                                 grant_config=dispatch_grant_config,
                                                 timeout_seconds=request.get("timeout_seconds", DEFAULT_FUNCTION_TIMEOUT))
        elif entry.host_execution:
            resp = self._execute_host_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=dispatch_grant_config,
                request_context=request_context,
            )
        else:
            resp = self._execute_user_function(
                principal_id=principal_id,
                entry=entry,
                args=args,
                request_id=request_id,
                start_time=start_time,
                grant_config=dispatch_grant_config,
                request_context=request_context,
            )
        resp = self._response_after_host_intent_handling(
            resp,
            entry=entry,
            principal_id=principal_id,
            request_context=request_context,
            start_time=start_time,
        )
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

    def _caller_requires_diagnostic(
        self,
        *,
        principal_id,
        caller_requires,
        request_context,
        principal_is_trusted_builtin,
        caller_ok,
        permission_id=None,
        handler_id=None,
        entry=None,
    ) -> dict[str, Any]:
        context = request_context if isinstance(request_context, dict) else {}
        authority = context.get("authority") if isinstance(context.get("authority"), dict) else {}
        approval_tokens = authority.get("approval_tokens")
        approval_token_keys = sorted(str(key) for key in approval_tokens.keys()) if isinstance(approval_tokens, dict) else []
        required = {str(item or "").strip() for item in caller_requires or []}
        if not principal_is_trusted_builtin:
            reason = "principal_not_trusted_builtin"
        elif not isinstance(request_context, dict):
            reason = "missing_request_context"
        elif context.get("_tool_server_approved") is not True:
            reason = "tool_server_approval_missing"
        elif not (required and required <= {"user.approved.high_risk"}):
            reason = "unsupported_caller_requirement"
        elif not caller_ok:
            reason = "permission_manager_or_context_denied"
        else:
            reason = "allowed"
        return {
            "reason": reason,
            "principal_id": str(principal_id or ""),
            "permission_id": str(permission_id or ""),
            "handler_id": str(handler_id or ""),
            "pack_id": str(getattr(entry, "pack_id", "") or "") if entry is not None else "",
            "function_id": str(getattr(entry, "function_id", "") or "") if entry is not None else "",
            "qualified_name": str(getattr(entry, "qualified_name", "") or "") if entry is not None else "",
            "caller_requires": sorted(required),
            "high_risk_approval_only": self._caller_requires_high_risk_approval_only(caller_requires),
            "principal_is_trusted_builtin": bool(principal_is_trusted_builtin),
            "context_is_dict": isinstance(request_context, dict),
            "tool_server_approved": context.get("_tool_server_approved") is True,
            "context_source": str(context.get("source") or ""),
            "context_approval_id": str(context.get("approval_id") or ""),
            "context_request_id": str(context.get("request_id") or ""),
            "context_conversation_id": str(context.get("conversation_id") or ""),
            "authority_principal_id": str(context.get("authority_principal_id") or ""),
            "authority_request_id": str(authority.get("request_id") or ""),
            "authority_permission_id": str(authority.get("permission_id") or ""),
            "authority_has_token": bool(authority.get("approval_token")),
            "authority_approval_token_keys": approval_token_keys,
            "context_keys": sorted(str(key) for key in context.keys())[:40],
        }

    def _log_caller_requires_denied(
        self,
        *,
        principal_id,
        caller_requires,
        request_context,
        principal_is_trusted_builtin,
        caller_ok,
        permission_id=None,
        handler_id=None,
        entry=None,
    ) -> None:
        diagnostic = self._caller_requires_diagnostic(
            principal_id=principal_id,
            caller_requires=caller_requires,
            request_context=request_context,
            principal_is_trusted_builtin=principal_is_trusted_builtin,
            caller_ok=caller_ok,
            permission_id=permission_id,
            handler_id=handler_id,
            entry=entry,
        )
        logger.warning("caller_requires denied: %s", json.dumps(diagnostic, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _caller_requires_high_risk_approval_only(caller_requires):
        required = {str(item or "").strip() for item in caller_requires or []}
        return bool(required) and required <= {"user.approved.high_risk"}

    def _sandbox_execution_context(
        self,
        request_context: dict[str, Any] | None,
        *,
        principal_id: str,
        entry,
        request_id: str,
        grant_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        source = request_context if isinstance(request_context, dict) else {}
        context = {
            key: self._sandbox_public_value(source[key])
            for key in (
                "conversation_id",
                "chat_id",
                "message_id",
                "source_message_id",
                "workspace_id",
                "locale",
                "timezone",
                "language",
                "run_source",
                "source",
            )
            if key in source and not self._sandbox_context_key_is_sensitive(key)
        }
        context.update(
            {
                "principal_id": str(principal_id or ""),
                "profile_id": self._principal_profile_id(principal_id, request_context),
                "pack_id": str(getattr(entry, "pack_id", "") or ""),
                "function_id": str(getattr(entry, "function_id", "") or ""),
                "request_id": request_id,
                "ts": self._now_ts(),
                "grant_config": self._sandbox_public_grant_config(grant_config),
            }
        )
        return context

    @classmethod
    def _sandbox_public_grant_config(cls, grant_config: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(grant_config, dict):
            return {}
        public_keys = {
            "allowed_kinds",
            "allowed_models",
            "allowed_packs",
            "allowed_path_globs",
            "allowed_providers",
            "allowed_target_packs",
            "expires_at_epoch",
            "max_daily_sends_per_scope",
            "max_output_bytes",
            "max_payload_bytes",
            "max_sends_per_scope",
            "model_ids",
            "provider_ids",
            "send_scope_level",
            "timeout",
        }
        return {
            key: cls._sandbox_public_value(value)
            for key, value in grant_config.items()
            if isinstance(key, str)
            and key in public_keys
            and not cls._sandbox_context_key_is_sensitive(key)
        }

    @classmethod
    def _sandbox_public_value(cls, value: Any, *, depth: int = 0) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if depth >= 4:
            return None
        if isinstance(value, (list, tuple)):
            return [cls._sandbox_public_value(item, depth=depth + 1) for item in list(value)[:64]]
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in list(value.items())[:64]:
                if not isinstance(key, str) or cls._sandbox_context_key_is_sensitive(key):
                    continue
                sanitized = cls._sandbox_public_value(item, depth=depth + 1)
                if sanitized is not None:
                    result[key] = sanitized
            return result
        return str(value)

    @staticmethod
    def _sandbox_context_key_is_sensitive(key: str) -> bool:
        normalized = str(key or "").strip().lower()
        if not normalized:
            return True
        if normalized.startswith("_"):
            return True
        return any(
            marker in normalized
            for marker in (
                "api_key",
                "approval",
                "auth",
                "bearer",
                "credential",
                "csrf",
                "keychain",
                "local_auth",
                "password",
                "secret",
                "session",
                "token",
            )
        )

    def _managed_sandbox_response_if_required(
        self,
        *,
        entry,
        principal_id: str,
        args: dict[str, Any] | None,
        request_id: str,
        start_time: float,
        request_context: dict[str, Any] | None,
        calling_convention: str,
        timeout_seconds: float | None = None,
        grant_config: dict[str, Any] | None = None,
    ) -> CapabilityResponse | None:
        if not self._entry_requires_managed_sandbox(entry, principal_id, request_context):
            return None
        if self._development_host_boundary_allowed(principal_id, request_context):
            return None

        supervisor = self._managed_sandbox_supervisor()
        if supervisor is None:
            return self._managed_sandbox_unavailable_response(
                entry=entry,
                principal_id=principal_id,
                request_id=request_id,
                start_time=start_time,
                calling_convention=calling_convention,
                reason="Managed sandbox runtime is not registered",
            )
        execute = getattr(supervisor, "execute_capability", None)
        if not callable(execute):
            return self._managed_sandbox_unavailable_response(
                entry=entry,
                principal_id=principal_id,
                request_id=request_id,
                start_time=start_time,
                calling_convention=calling_convention,
                reason="Managed sandbox supervisor cannot execute capabilities",
            )
        try:
            function_dir = getattr(entry, "function_dir", None)
            main_py_path = getattr(entry, "main_py_path", None)
            entrypoint = str(getattr(entry, "entrypoint", "") or "main.py:run")
            sandbox_context = self._sandbox_execution_context(
                request_context,
                principal_id=principal_id,
                entry=entry,
                request_id=request_id,
                grant_config=grant_config,
            )
            result = execute(
                {
                    "execution_boundary": ExecutionBoundary.MANAGED_SANDBOX.value,
                    "profile_runtime": profile_runtime_name(self._principal_profile_id(principal_id, request_context)),
                    "principal_id": principal_id,
                    "request_id": request_id,
                    "pack_id": str(getattr(entry, "pack_id", "") or ""),
                    "function_id": str(getattr(entry, "function_id", "") or ""),
                    "qualified_name": str(getattr(entry, "qualified_name", "") or ""),
                    "calling_convention": str(calling_convention or ""),
                    "function_dir": str(function_dir) if function_dir is not None else "",
                    "main_py_path": str(main_py_path) if main_py_path is not None else "",
                    "entrypoint": entrypoint,
                    "timeout_seconds": float(timeout_seconds or self._get_function_timeout(entry)),
                    "runner_path": str(FUNCTION_RUNNER_PATH),
                    "args": dict(args or {}),
                    "context": sandbox_context,
                }
            )
        except Exception as exc:
            return self._managed_sandbox_unavailable_response(
                entry=entry,
                principal_id=principal_id,
                request_id=request_id,
                start_time=start_time,
                calling_convention=calling_convention,
                reason=f"Managed sandbox execution failed: {exc}",
            )
        if isinstance(result, CapabilityResponse):
            return result
        if isinstance(result, dict) and result and (
            isinstance(result.get("success"), bool) or isinstance(result.get("ok"), bool)
        ):
            success = result.get("success") if isinstance(result.get("success"), bool) else result.get("ok")
            return CapabilityResponse(
                success=success,
                output=result.get("output", result),
                error=None if success else str(result.get("error") or "Managed sandbox execution failed"),
                error_type=None if success else str(result.get("error_type") or "managed_sandbox_error"),
                latency_ms=(time.time() - start_time) * 1000,
            )
        return CapabilityResponse(
            success=False,
            output={
                "execution_boundary": ExecutionBoundary.MANAGED_SANDBOX.value,
                "required": True,
                "pack_id": str(getattr(entry, "pack_id", "") or ""),
                "function_id": str(getattr(entry, "function_id", "") or ""),
                "qualified_name": str(getattr(entry, "qualified_name", "") or ""),
                "calling_convention": str(calling_convention or ""),
                "request_id": request_id,
            },
            error="Managed sandbox returned an invalid response",
            error_type="managed_sandbox_error",
            latency_ms=(time.time() - start_time) * 1000,
        )

    def _entry_requires_managed_sandbox(
        self,
        entry,
        principal_id: str,
        request_context: dict[str, Any] | None = None,
    ) -> bool:
        del principal_id
        pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        pack_root_hint = getattr(entry, "function_dir", None) or getattr(entry, "main_py_path", None)
        if self._is_core_builtin_trust_bypass_entry(entry):
            return False
        if self._is_trusted_builtin_pack(pack_id, pack_root_hint=pack_root_hint):
            return False
        return True

    def _handler_def_requires_managed_sandbox(self, handler_def, principal_id: str) -> bool:
        del principal_id
        pack_id = str(getattr(handler_def, "pack_id", "") or "").strip()
        entry = types.SimpleNamespace(
            pack_id=pack_id,
            function_dir=getattr(handler_def, "handler_dir", None),
            main_py_path=getattr(handler_def, "handler_py_path", None),
        )
        if self._is_core_builtin_trust_bypass_entry(entry):
            return False
        if pack_id and self._is_trusted_builtin_pack(pack_id, pack_root_hint=getattr(handler_def, "handler_dir", None)):
            return False
        return True

    @staticmethod
    def _development_host_boundary_allowed(
        principal_id: str,
        request_context: dict[str, Any] | None,
    ) -> bool:
        environment = str(os.environ.get("RUMI_ENVIRONMENT", "")).strip().lower()
        if environment not in {"development", "dev"}:
            return False
        if str(os.environ.get("RUMI_ALLOW_DEVELOPMENT_HOST_EXECUTION", "")).strip().lower() not in {"1", "true"}:
            return False
        if str(principal_id or "").startswith("profile:"):
            return False
        context = request_context if isinstance(request_context, dict) else {}
        principal = context.get("_authenticated_principal")
        if isinstance(principal, dict):
            if str(principal.get("auth_mode") or "").strip() == "scoped_bearer":
                return False
            if str(principal.get("surface_id") or "").strip().startswith("mobile"):
                return False
        return True

    @staticmethod
    def _principal_profile_id(principal_id: str, request_context: dict[str, Any] | None) -> str:
        context = request_context if isinstance(request_context, dict) else {}
        principal = context.get("_authenticated_principal")
        if isinstance(principal, dict) and str(principal.get("profile_id") or "").strip():
            return str(principal.get("profile_id") or "").strip()
        text = str(principal_id or "").strip()
        if text.startswith("profile:"):
            return text.split(":", 1)[1].split("__", 1)[0]
        return text or "default"

    @staticmethod
    def _managed_sandbox_supervisor():
        try:
            from .di_container import get_container as _get_di_container

            return _get_di_container().get_or_none("managed_sandbox_supervisor")
        except Exception:
            return None

    def _managed_sandbox_unavailable_response(
        self,
        *,
        entry,
        principal_id: str,
        request_id: str,
        start_time: float,
        calling_convention: str,
        reason: str,
    ) -> CapabilityResponse:
        profile_id = self._principal_profile_id(principal_id, None)
        return CapabilityResponse(
            success=False,
            output={
                "execution_boundary": ExecutionBoundary.MANAGED_SANDBOX.value,
                "required": True,
                "profile_runtime": profile_runtime_name(profile_id),
                "pack_id": str(getattr(entry, "pack_id", "") or ""),
                "function_id": str(getattr(entry, "function_id", "") or ""),
                "qualified_name": str(getattr(entry, "qualified_name", "") or ""),
                "calling_convention": str(calling_convention or ""),
                "request_id": request_id,
            },
            error=reason,
            error_type=SANDBOX_RUNTIME_UNAVAILABLE,
            latency_ms=(time.time() - start_time) * 1000,
        )

    @staticmethod
    def _is_host_capability_pack(pack_id: str) -> bool:
        return str(pack_id or "").strip() == "rumi_host_capabilities_pack"

    @staticmethod
    def _entry_declares_direct_host_access(entry) -> bool:
        manifest = getattr(entry, "manifest", None)
        if not isinstance(manifest, dict):
            manifest = {}
        calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
        configured_host_entry = bool(
            getattr(entry, "host_execution", False)
            and (getattr(entry, "function_dir", None) or getattr(entry, "main_py_path", None))
        )
        return bool(
            manifest.get("host_operation")
            or manifest.get("host_execution") is True
            or configured_host_entry
            or calling_convention == "python_host"
        )

    def _critical_host_confirmation_required_response(
        self,
        *,
        entry,
        principal_id: str,
        request_id: str,
        start_time: float,
        request_context: dict[str, Any] | None = None,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResponse | None:
        phrase = self._host_confirmation_phrase_for_entry(entry)
        manifest = getattr(entry, "manifest", None)
        args_hash = self._host_execution_args_hash(args)
        resource = {
            "kind": "critical_host_function",
            "pack_id": getattr(entry, "pack_id", ""),
            "function_id": getattr(entry, "function_id", ""),
            "function_qualified_name": getattr(entry, "qualified_name", ""),
            "calling_convention": getattr(entry, "calling_convention", None),
            "host_operation": manifest.get("host_operation") if isinstance(manifest, dict) else None,
            "args_hash": args_hash,
            "args_summary": self._host_execution_args_summary(args),
            "confirmation_phrase": phrase,
            "typed_confirmation_required": True,
        }
        try:
            from .authority import get_authority_service

            authority_request_id, approval_token = self._authority_context_token_for_permission(
                request_context,
                "host.process.exec_guarded",
            )
            decision = get_authority_service().check(
                principal_id=principal_id,
                permission_id="host.process.exec_guarded",
                resource=resource,
                reason="Direct host execution requires typed confirmation",
                request_id=authority_request_id or request_id or None,
                approval_token=approval_token or None,
            )
            if decision.allowed and not decision.approval_required:
                return None
            event = decision.to_approval_event() if decision.approval_required else decision.to_dict()
        except Exception:
            event = {
                "approval_required": True,
                "permission_id": "host.process.exec_guarded",
                "resource": resource,
                "risk_level": "critical",
            }
        event.update(
            {
                "approval_kind": "critical_host_function",
                "critical": True,
                "typed_confirmation_required": True,
                "confirmation_phrase": phrase,
            }
        )
        return CapabilityResponse(
            success=False,
            output=event,
            error="Critical host confirmation required",
            error_type="critical_host_confirmation_required",
            latency_ms=(time.time() - start_time) * 1000,
        )

    def _host_boundary_response_if_needed(
        self,
        *,
        entry,
        principal_id: str,
        request_id: str,
        start_time: float,
        request_context: dict[str, Any] | None = None,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResponse | None:
        pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        if self._is_host_capability_pack(pack_id):
            return None
        if not self._entry_declares_direct_host_access(entry):
            return None
        return self._critical_host_confirmation_required_response(
            entry=entry,
            principal_id=principal_id,
            request_id=request_id,
            start_time=start_time,
            request_context=request_context,
            args=args,
        )

    @staticmethod
    def _host_confirmation_phrase_for_entry(entry) -> str:
        manifest = getattr(entry, "manifest", None)
        manifest = manifest if isinstance(manifest, dict) else {}
        seed = "|".join(
            str(value or "").strip()
            for value in (
                getattr(entry, "pack_id", ""),
                getattr(entry, "function_id", ""),
                getattr(entry, "qualified_name", ""),
                getattr(entry, "calling_convention", ""),
                manifest.get("host_operation"),
            )
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8].upper()
        return f"RUMI-HOST-{digest}"

    @staticmethod
    def _host_execution_args_hash(args: dict[str, Any] | None) -> str:
        normalized = args if isinstance(args, dict) else {}
        payload = json.dumps(
            {"args": normalized},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _host_execution_args_summary(args: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(args, dict):
            return {"type": type(args).__name__, "keys": [], "count": 0}
        visible_keys = sorted(str(key) for key in args.keys() if not _is_sensitive_arg_key(key))
        redacted_field_count = len(args) - len(visible_keys)
        summary: dict[str, Any] = {
            "type": "object",
            "keys": visible_keys[:20],
            "count": len(visible_keys),
            "truncated": len(visible_keys) > 20,
        }
        tokens = _host_command_tokens(args)
        paths: list[str] = []
        urls: list[str] = []
        if tokens:
            summary["executable"] = tokens[0]
            summary["argument_count"] = max(0, len(tokens) - 1)
            _collect_host_targets_from_command_tokens(tokens[1:], paths=paths, urls=urls)
        for key in ("cwd", "working_dir", "working_directory"):
            if key in args and not _is_sensitive_arg_key(key):
                cwd = _safe_host_summary_text(args.get(key))
                if cwd:
                    summary["cwd"] = cwd
                break
        for key, value in args.items():
            if str(key) in {"cwd", "working_dir", "working_directory"}:
                continue
            if _is_sensitive_arg_key(key) or not _is_target_arg_key(key):
                continue
            _collect_host_targets(value, paths=paths, urls=urls)
        if paths:
            summary["target_paths"] = paths
        if urls:
            summary["target_urls"] = urls
        if redacted_field_count:
            summary["redacted_field_count"] = redacted_field_count
        return summary

    @staticmethod
    def _authority_context_token_for_permission(
        request_context: dict[str, Any] | None,
        permission_id: str,
    ) -> tuple[str, str]:
        permission_id = str(permission_id or "").strip()
        if not permission_id or not isinstance(request_context, dict):
            return "", ""

        def from_mapping(raw: Any) -> tuple[str, str]:
            if not isinstance(raw, dict):
                return "", ""
            if str(raw.get("permission_id") or "").strip() not in {"", permission_id}:
                return "", ""
            authority_request_id = str(raw.get("request_id") or raw.get("approval_request_id") or "").strip()
            token = str(raw.get("approval_token") or raw.get("token") or "").strip()
            if authority_request_id and token:
                return authority_request_id, token
            return "", ""

        for container in (request_context.get("authority"), request_context):
            if not isinstance(container, dict):
                continue
            approvals = container.get("approval_tokens")
            if isinstance(approvals, dict):
                direct = from_mapping(approvals.get(permission_id))
                if direct != ("", ""):
                    return direct
            approvals_list = container.get("approvals")
            if isinstance(approvals, list):
                approvals_list = approvals
            if isinstance(approvals_list, list):
                for item in approvals_list:
                    direct = from_mapping(item)
                    if direct != ("", ""):
                        return direct
            direct = from_mapping(container)
            if direct != ("", ""):
                return direct
        return "", ""

    def _response_after_host_intent_handling(
        self,
        resp: CapabilityResponse,
        *,
        entry,
        principal_id: str,
        request_context: dict[str, Any] | None,
        start_time: float,
    ) -> CapabilityResponse:
        if not resp.success:
            return resp
        try:
            from .host_intent import maybe_handle_host_intent_output

            caller_pack_id, caller_function_id = self._host_intent_caller_ids(entry, request_context)
            handled = maybe_handle_host_intent_output(
                resp.output,
                principal_id=principal_id,
                caller_pack_id=caller_pack_id,
                caller_function_id=caller_function_id,
                request_context=request_context,
            )
        except Exception as exc:
            return CapabilityResponse(
                success=False,
                error=f"Host intent handling failed: {exc}",
                error_type="host_intent_error",
                latency_ms=(time.time() - start_time) * 1000,
            )
        if handled is None:
            return resp
        return CapabilityResponse(
            success=bool(handled.get("success")),
            output=handled,
            error=None if handled.get("success") else str(handled.get("error_type") or "Host intent requires approval"),
            error_type=None if handled.get("success") else str(handled.get("error_type") or "host_intent_approval_required"),
            latency_ms=(time.time() - start_time) * 1000,
        )

    def _host_intent_caller_ids(self, entry, request_context: dict[str, Any] | None) -> tuple[str, str]:
        entry_pack_id = str(getattr(entry, "pack_id", "") or "").strip()
        entry_function_id = str(getattr(entry, "function_id", "") or "").strip()
        if entry_function_id == "ambient_monitor_start":
            return "rumi_ambient_trigger_pack", "ambient_monitor_start"
        if self._is_host_capability_pack(entry_pack_id):
            context = request_context if isinstance(request_context, dict) else {}
            delegated_pack_id = self._first_context_string(
                context,
                "caller_pack_id",
                "owner_pack",
                "_source_pack_id",
            )
            delegated_function_id = self._first_context_string(
                context,
                "caller_function_id",
                "function_id",
                "_source_function_id",
            )
            if delegated_pack_id and delegated_function_id:
                return delegated_pack_id, delegated_function_id
        return entry_pack_id, entry_function_id

    @staticmethod
    def _first_context_string(context: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = str(context.get(key) or "").strip()
            if value:
                return value
        return ""

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
        manifest = getattr(entry, "manifest", None)
        grant_config = manifest.get("grant_config", {}) if isinstance(manifest, dict) else {}
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

    def _execute_user_function(
        self,
        principal_id,
        entry,
        args,
        request_id,
        start_time,
        grant_config=None,
        request_context=None,
        force_docker=False,
        timeout_seconds=None,
    ):
        runtime = getattr(entry, 'runtime', 'python')
        if runtime == "binary":
            guard_resp = self._host_runtime_guard(entry, runtime, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_binary_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, grant_config=grant_config, request_context=request_context, timeout_seconds=timeout_seconds)
        elif runtime == "command":
            guard_resp = self._host_runtime_guard(entry, runtime, start_time)
            if guard_resp is not None:
                return guard_resp
            return self._execute_command_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, grant_config=grant_config, request_context=request_context, timeout_seconds=timeout_seconds)
        if getattr(entry, "host_execution", False) and runtime != "python":
            return CapabilityResponse(success=False, error=f"runtime='{runtime}' requires Docker execution (host_execution must be false)",
                                      error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        timeout = min(float(timeout_seconds or self._get_function_timeout(entry)), MAX_TIMEOUT)
        if function_dir is None and main_py_path is None:
            return CapabilityResponse(success=False, error="User function execution is not configured", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        sandbox_resp = self._managed_sandbox_response_if_required(
            entry=entry,
            principal_id=principal_id,
            args=args,
            request_id=request_id,
            start_time=start_time,
            request_context=request_context,
            calling_convention=(
                "python_docker"
                if force_docker
                else str(getattr(entry, "calling_convention", None) or runtime)
            ),
            timeout_seconds=timeout_seconds,
            grant_config=grant_config,
        )
        if sandbox_resp is not None:
            return sandbox_resp
        if self._is_docker_available() and _DockerRunBuilder is not None:
            return self._execute_user_function_docker(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout, grant_config=grant_config, request_context=request_context)
        else:
            logger.warning("Docker not available for user function %s:%s.", pack_id, function_id)
            if force_docker:
                return CapabilityResponse(success=False, error="Docker is not available for python_docker function execution.", error_type="docker_unavailable", latency_ms=(time.time() - start_time) * 1000)
            security_mode = os.environ.get("RUMI_SECURITY_MODE", "").strip().lower()
            function_docker_policy = os.environ.get("RUMI_FUNCTION_DOCKER_POLICY", "").strip().lower()
            if security_mode == "strict" or function_docker_policy == "strict":
                return CapabilityResponse(success=False, error="Docker is not available and strict function isolation forbids host fallback.", error_type="docker_unavailable", latency_ms=(time.time() - start_time) * 1000)
            allow_fallback = os.environ.get("RUMI_ALLOW_HOST_FALLBACK", "").lower()
            if allow_fallback not in ("1", "true"):
                return CapabilityResponse(success=False, error="Docker is not available and host fallback is disabled. Set RUMI_ALLOW_HOST_FALLBACK=1 to enable.", error_type="docker_unavailable", latency_ms=(time.time() - start_time) * 1000)
            return self._execute_user_function_host(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout, grant_config=grant_config, request_context=request_context)

    def _execute_user_function_docker(self, principal_id, entry, args, request_id, start_time, timeout, grant_config=None, request_context=None):
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir = Path(entry.function_dir)
        container_name = f"rumi-func-{pack_id}-{function_id}-{uuid.uuid4().hex[:8]}"
        runner_path = FUNCTION_RUNNER_PATH.resolve()
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "pack_id": pack_id, "function_id": function_id, "request_id": request_id, "ts": self._now_ts(), "grant_config": dict(grant_config or {})})
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
            builder.env("RUMI_PACK_ID", pack_id)
            builder.env("RUMI_FUNCTION_ID", function_id)
            builder.label("rumi.managed", "true")
            builder.label("rumi.type", "function")
            builder.label("rumi.pack_id", pack_id)
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

    def _execute_user_function_host(self, principal_id, entry, args, request_id, start_time, timeout, grant_config=None, request_context=None):
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts(), "grant_config": dict(grant_config or {})})
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

    def _execute_host_function(self, principal_id, entry, args, request_id, start_time, grant_config=None, request_context=None, timeout_seconds=None):
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        if function_dir is None and main_py_path is None:
            return CapabilityResponse(success=False, error="Host function execution is not configured", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        allow_host = os.environ.get("RUMI_ALLOW_HOST_EXECUTION", "").lower()
        if allow_host not in ("1", "true"):
            return CapabilityResponse(success=False, error="Host execution is disabled. Set RUMI_ALLOW_HOST_EXECUTION=1 to enable.", error_type="host_execution_disabled", latency_ms=(time.time() - start_time) * 1000)
        timeout = min(float(timeout_seconds or self._get_function_timeout(entry)), MAX_TIMEOUT)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts(), "grant_config": dict(grant_config or {})})
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

    def _execute_binary_function(self, principal_id, entry, args, request_id, start_time, grant_config=None, request_context=None, timeout_seconds=None):
        guard_resp = self._host_runtime_guard(entry, "binary", start_time)
        if guard_resp is not None:
            return guard_resp
        binary_path = entry.main_binary_path
        if binary_path is None or not Path(binary_path).is_file():
            return CapabilityResponse(success=False, error=f"Binary not found: {binary_path}", error_type="binary_not_found", latency_ms=(time.time() - start_time) * 1000)
        func_dir = Path(entry.function_dir).resolve()
        if not Path(binary_path).resolve().is_relative_to(func_dir):
            return CapabilityResponse(success=False, error="Binary path escapes function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        timeout = min(float(timeout_seconds or self._get_function_timeout(entry)), MAX_TIMEOUT)
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts(), "grant_config": dict(grant_config or {})})
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        try:
            proc = subprocess.run([str(binary_path)], input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=_sanitize_error(f"Binary exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}"), error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=json.loads(stdout), latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except json.JSONDecodeError:
            return CapabilityResponse(success=False, error="Output is not valid JSON", error_type="invalid_json_output", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_command_function(self, principal_id, entry, args, request_id, start_time, grant_config=None, request_context=None, timeout_seconds=None):
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
            else:
                return CapabilityResponse(success=False, error="Command entrypoints must use an absolute executable path", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        elif not Path(command[0]).is_absolute():
            return CapabilityResponse(success=False, error="Command entrypoints must use an absolute executable path", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        timeout = min(float(timeout_seconds or self._get_function_timeout(entry)), MAX_TIMEOUT)
        context = dict(request_context or {}) if isinstance(request_context, dict) else {}
        context.update({"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts(), "grant_config": dict(grant_config or {})})
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        func_dir = Path(entry.function_dir).resolve() if entry.function_dir else None
        try:
            proc = subprocess.run(command, input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir) if func_dir else None)
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=_sanitize_error(f"Command exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}"), error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
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
        if not hasattr(_flow_call_stack_local, "stack"):
            _flow_call_stack_local.stack = []
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
        if self._handler_def_requires_managed_sandbox(handler_def, principal_id):
            entry = types.SimpleNamespace(
                pack_id=str(getattr(handler_def, "pack_id", "") or ""),
                function_id=str(getattr(handler_def, "handler_id", "") or ""),
                qualified_name=str(getattr(handler_def, "handler_id", "") or ""),
                function_dir=getattr(handler_def, "handler_dir", None),
                main_py_path=getattr(handler_def, "handler_py_path", None),
                is_builtin=bool(getattr(handler_def, "is_builtin", False)),
                calling_convention="subprocess",
            )
            sandbox_resp = self._managed_sandbox_response_if_required(
                entry=entry,
                principal_id=principal_id,
                args=args,
                request_id=request_id,
                start_time=start_time,
                request_context=request_context,
                calling_convention="subprocess",
                timeout_seconds=timeout_seconds,
                grant_config=grant_config,
            )
            if sandbox_resp is not None:
                return sandbox_resp
        entrypoint = str(handler_def.entrypoint or "main.py:run")
        ep_file, ep_func = (
            entrypoint.rsplit(":", 1) if ":" in entrypoint else (entrypoint, "run")
        )
        try:
            handler_dir = Path(handler_def.handler_dir).resolve()
            handler_py_path = (handler_dir / ep_file).resolve()
            handler_py_path.relative_to(handler_dir)
            trusted_handler_path = Path(handler_def.handler_py_path).resolve()
        except (OSError, ValueError, TypeError):
            return CapabilityResponse(success=False, error="Invalid handler entrypoint", error_type="invalid_entrypoint", latency_ms=(time.time() - start_time) * 1000)
        if trusted_handler_path != handler_py_path:
            return CapabilityResponse(success=False, error="Handler entrypoint does not match trusted registry path", error_type="invalid_entrypoint", latency_ms=(time.time() - start_time) * 1000)
        if not handler_py_path.is_file():
            return CapabilityResponse(success=False, error="Handler entrypoint not found", error_type="entrypoint_not_found", latency_ms=(time.time() - start_time) * 1000)
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
            if trusted is not None:
                details["trusted"] = trusted
            if grant_allowed is not None:
                details["grant_allowed"] = grant_allowed
            if grant_reason is not None:
                details["grant_reason"] = grant_reason
            if detail_reason is not None:
                details["detail_reason"] = detail_reason
            if extra_details:
                details.update(extra_details)
            if response.error:
                details["error"] = response.error
                details["error_type"] = response.error_type
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
