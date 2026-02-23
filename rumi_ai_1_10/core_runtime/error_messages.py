"""
error_messages.py - 統一エラーメッセージ基盤 (Wave 13 T-056)

エラーコード体系、RumiError クラス、ヘルパー関数を提供する。
既存モジュールへの段階的適用を想定した基盤モジュール。

エラーコード形式: RUMI-{カテゴリ}-{3桁番号}
カテゴリ: AUTH, NET, FLOW, PACK, CAP, VAL, SYS

設計原則:
- stdlib のみに依存（循環参照を作らない）
- スレッドセーフ（状態を持たない純粋関数のみ）
- Python 3.9+ 互換
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


# ======================================================================
# エラーコード形式
# ======================================================================

# RUMI-{CATEGORY(2-5大文字)}-{3桁番号}
ERROR_CODE_PATTERN = re.compile(r'^RUMI-[A-Z]{2,5}-\d{3}$')


# ======================================================================
# カテゴリ列挙型
# ======================================================================

class ErrorCategory(enum.Enum):
    """エラーカテゴリ。

    AUTH — 認証・認可
    NET  — ネットワーク
    FLOW — フロー実行
    PACK — Pack 管理
    CAP  — Capability
    VAL  — バリデーション
    SYS  — システム全般
    """

    AUTH = "AUTH"
    NET = "NET"
    FLOW = "FLOW"
    PACK = "PACK"
    CAP = "CAP"
    VAL = "VAL"
    SYS = "SYS"


# ======================================================================
# ErrorCode データクラス（定数テンプレート）
# ======================================================================

@dataclass(frozen=True)
class ErrorCode:
    """エラーコード定数。テンプレート文字列とデフォルト suggestion を保持する。

    Attributes:
        code: RUMI-{CAT}-{NNN} 形式のコード文字列。
        template: ``str.format()`` 対応のメッセージテンプレート。
        suggestion: デフォルトの解決策提案（format_error でオーバーライド可）。
        category: 所属カテゴリ。
    """

    code: str
    template: str
    suggestion: Optional[str] = None
    category: Optional[ErrorCategory] = None

    def __post_init__(self) -> None:
        if not ERROR_CODE_PATTERN.match(self.code):
            raise ValueError(
                f"Invalid error code format: {self.code!r}. "
                f"Expected RUMI-{{CATEGORY}}-{{NNN}}"
            )


# ======================================================================
# RumiError 例外クラス
# ======================================================================

class RumiError(Exception):
    """統一エラークラス。

    Attributes:
        code: エラーコード文字列。
        message: 人間可読メッセージ。
        details: 追加情報の dict（任意）。
        suggestion: 解決策の提案（任意）。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.suggestion = suggestion
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        parts = [f"code={self.code!r}", f"message={self.message!r}"]
        if self.details is not None:
            parts.append(f"details={self.details!r}")
        if self.suggestion is not None:
            parts.append(f"suggestion={self.suggestion!r}")
        return f"RumiError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """JSON シリアライズ可能な dict を返す。

        ``details`` / ``suggestion`` が ``None`` の場合はキー自体を含めない。
        """
        result: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        return result


# ======================================================================
# エラーコード定数 — AUTH (認証・認可)
# ======================================================================

AUTH_TOKEN_INVALID = ErrorCode(
    code="RUMI-AUTH-001",
    template="Authentication token is invalid",
    suggestion="Provide a valid authentication token.",
    category=ErrorCategory.AUTH,
)

AUTH_TOKEN_EXPIRED = ErrorCode(
    code="RUMI-AUTH-002",
    template="Authentication token has expired",
    suggestion="Refresh or re-issue the authentication token.",
    category=ErrorCategory.AUTH,
)

AUTH_PERMISSION_DENIED = ErrorCode(
    code="RUMI-AUTH-003",
    template="Permission denied: {reason}",
    suggestion="Check the required permissions for this operation.",
    category=ErrorCategory.AUTH,
)

# ======================================================================
# エラーコード定数 — NET (ネットワーク)
# ======================================================================

NET_CONNECTION_FAILED = ErrorCode(
    code="RUMI-NET-001",
    template="Network connection failed: {target}",
    suggestion="Check network connectivity and target address.",
    category=ErrorCategory.NET,
)

NET_REQUEST_TIMEOUT = ErrorCode(
    code="RUMI-NET-002",
    template="Request timed out after {timeout_seconds}s: {target}",
    suggestion="Increase the timeout or check the target service status.",
    category=ErrorCategory.NET,
)

NET_PROXY_ERROR = ErrorCode(
    code="RUMI-NET-003",
    template="Proxy error for {target}: {reason}",
    suggestion="Check proxy configuration and target service availability.",
    category=ErrorCategory.NET,
)

# ======================================================================
# エラーコード定数 — FLOW (フロー実行)
# ======================================================================

FLOW_NOT_FOUND = ErrorCode(
    code="RUMI-FLOW-001",
    template="Flow definition not found: {flow_id}",
    suggestion="Verify the flow_id and ensure the flow file exists.",
    category=ErrorCategory.FLOW,
)

FLOW_EXECUTION_ERROR = ErrorCode(
    code="RUMI-FLOW-002",
    template="Flow execution failed: {flow_id} at step {step}",
    suggestion="Check the flow definition and step configuration.",
    category=ErrorCategory.FLOW,
)

FLOW_STEP_FAILED = ErrorCode(
    code="RUMI-FLOW-003",
    template="Flow step failed: {step} in {flow_id}: {reason}",
    suggestion="Review the step implementation and input data.",
    category=ErrorCategory.FLOW,
)

# ======================================================================
# エラーコード定数 — PACK (Pack 管理)
# ======================================================================

PACK_ID_INVALID = ErrorCode(
    code="RUMI-PACK-001",
    template="Invalid pack_id: {pack_id!r} (must match [a-zA-Z0-9_-]{{1,64}})",
    suggestion="Use only alphanumeric characters, underscores, and hyphens (1-64 chars).",
    category=ErrorCategory.PACK,
)

PACK_ECOSYSTEM_INVALID = ErrorCode(
    code="RUMI-PACK-002",
    template="ecosystem.json is invalid for pack {pack_id}: {reason}",
    suggestion="Validate ecosystem.json against the pack schema.",
    category=ErrorCategory.PACK,
)

PACK_ID_MISMATCH = ErrorCode(
    code="RUMI-PACK-003",
    template="pack_id mismatch: ecosystem.json declares {declared!r} but directory is {actual!r}",
    suggestion="Ensure pack_id in ecosystem.json matches the directory name.",
    category=ErrorCategory.PACK,
)

PACK_CONNECTIVITY_MISSING = ErrorCode(
    code="RUMI-PACK-004",
    template="Pack {pack_id} references {ref_pack_id} via ${{ctx}} but it is not in connectivity",
    suggestion="Add the referenced pack_id to the connectivity list in ecosystem.json.",
    category=ErrorCategory.PACK,
)

# ======================================================================
# エラーコード定数 — CAP (Capability)
# ======================================================================

CAP_NOT_FOUND = ErrorCode(
    code="RUMI-CAP-001",
    template="Capability not found: {capability_id}",
    suggestion="Check that the capability is installed and the ID is correct.",
    category=ErrorCategory.CAP,
)

CAP_EXECUTION_ERROR = ErrorCode(
    code="RUMI-CAP-002",
    template="Capability execution failed: {capability_id}: {reason}",
    suggestion="Review the capability implementation and input parameters.",
    category=ErrorCategory.CAP,
)

# ======================================================================
# エラーコード定数 — VAL (バリデーション)
# ======================================================================

VAL_EMPTY_VALUE = ErrorCode(
    code="RUMI-VAL-001",
    template="{field_name} must not be empty",
    suggestion="Provide a non-empty value.",
    category=ErrorCategory.VAL,
)

VAL_PATTERN_MISMATCH = ErrorCode(
    code="RUMI-VAL-002",
    template="{field_name} does not match required pattern {pattern}: {value!r}",
    suggestion="Ensure the value matches the expected pattern.",
    category=ErrorCategory.VAL,
)

VAL_PATH_TRAVERSAL = ErrorCode(
    code="RUMI-VAL-003",
    template="Path traversal detected: {path} is not within {base}",
    suggestion="Use a path that stays within the allowed directory.",
    category=ErrorCategory.VAL,
)

VAL_SYMLINK_DETECTED = ErrorCode(
    code="RUMI-VAL-004",
    template="Symbolic link detected (security risk): {path}",
    suggestion="Remove the symbolic link or use a regular file/directory.",
    category=ErrorCategory.VAL,
)

VAL_ENTRYPOINT_INVALID = ErrorCode(
    code="RUMI-VAL-005",
    template="Invalid entrypoint format (expected 'file:func'): {entrypoint}",
    suggestion="Use 'filename.py:function_name' format.",
    category=ErrorCategory.VAL,
)

VAL_FILE_NOT_FOUND = ErrorCode(
    code="RUMI-VAL-006",
    template="File not found: {filepath}",
    suggestion="Verify the file path exists.",
    category=ErrorCategory.VAL,
)

VAL_BODY_TOO_LARGE = ErrorCode(
    code="RUMI-VAL-007",
    template="Request body too large: {size} bytes (max {max_size} bytes)",
    suggestion="Reduce the request body size.",
    category=ErrorCategory.VAL,
)

# ======================================================================
# エラーコード定数 — SYS (システム全般)
# ======================================================================

SYS_INTERNAL_ERROR = ErrorCode(
    code="RUMI-SYS-001",
    template="Internal system error: {reason}",
    suggestion="This is an unexpected error. Please report it.",
    category=ErrorCategory.SYS,
)

SYS_CONFIG_ERROR = ErrorCode(
    code="RUMI-SYS-002",
    template="Configuration error: {reason}",
    suggestion="Check the configuration file and environment variables.",
    category=ErrorCategory.SYS,
)

SYS_DIRECTORY_NOT_FOUND = ErrorCode(
    code="RUMI-SYS-003",
    template="Directory does not exist: {directory}",
    suggestion="Create the directory or verify the path.",
    category=ErrorCategory.SYS,
)


# ======================================================================
# エラーコードレジストリ（自動収集）
# ======================================================================

_ALL_ERROR_CODES: Dict[str, ErrorCode] = {}


def _register_all() -> None:
    """モジュール内の全 ErrorCode インスタンスを自動収集して登録する。"""
    import sys

    module = sys.modules[__name__]
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, ErrorCode):
            if obj.code in _ALL_ERROR_CODES:
                raise ValueError(f"Duplicate error code: {obj.code}")
            _ALL_ERROR_CODES[obj.code] = obj


_register_all()


def get_all_error_codes() -> Dict[str, ErrorCode]:
    """登録済みの全エラーコードを ``{code: ErrorCode}`` dict で返す。"""
    return dict(_ALL_ERROR_CODES)


def get_error_code(code: str) -> Optional[ErrorCode]:
    """コード文字列から ErrorCode を取得する。見つからなければ ``None``。"""
    return _ALL_ERROR_CODES.get(code)


# ======================================================================
# ヘルパー関数
# ======================================================================

def format_error(
    code: ErrorCode,
    *,
    details: Optional[Dict[str, Any]] = None,
    suggestion: Optional[str] = None,
    **kwargs: Any,
) -> RumiError:
    """テンプレート文字列にパラメータを埋め込んで RumiError を返す。

    Args:
        code: ErrorCode 定数。
        details: 追加情報 dict（RumiError.details にセット）。
        suggestion: 解決策提案（指定しなければ ErrorCode のデフォルトを使用）。
        **kwargs: テンプレートに埋め込むパラメータ。

    Returns:
        組み立て済みの RumiError インスタンス。

    Example::

        err = format_error(
            AUTH_PERMISSION_DENIED,
            reason="admin role required",
            details={"user": "alice"},
        )
        # => RumiError(code='RUMI-AUTH-003',
        #              message='Permission denied: admin role required',
        #              details={'user': 'alice'},
        #              suggestion='Check the required permissions ...')
    """
    try:
        message = code.template.format(**kwargs)
    except KeyError as exc:
        message = f"{code.template} (missing parameter: {exc})"

    resolved_suggestion = suggestion if suggestion is not None else code.suggestion

    return RumiError(
        code=code.code,
        message=message,
        details=details,
        suggestion=resolved_suggestion,
    )
