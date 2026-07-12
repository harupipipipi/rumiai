"""
test_error_messages.py - error_messages モジュールのテスト (Wave 13 T-056)

RumiError クラス、ErrorCode データクラス、エラーコード定数、
format_error ヘルパーの網羅的なテストを行う。
"""

from __future__ import annotations

import json

import pytest

from core_runtime.error_messages import (
    ERROR_CODE_PATTERN,
    ErrorCategory,
    ErrorCode,
    RumiError,
    format_error,
    get_all_error_codes,
    get_error_code,
    # 定数 — AUTH
    AUTH_TOKEN_INVALID,
    AUTH_TOKEN_EXPIRED,
    AUTH_PERMISSION_DENIED,
    # 定数 — NET
    NET_CONNECTION_FAILED,
    NET_REQUEST_TIMEOUT,
    NET_PROXY_ERROR,
    # 定数 — FLOW
    FLOW_NOT_FOUND,
    FLOW_EXECUTION_ERROR,
    FLOW_STEP_FAILED,
    # 定数 — PACK
    PACK_ID_INVALID,
    PACK_ECOSYSTEM_INVALID,
    PACK_ID_MISMATCH,
    PACK_CONNECTIVITY_MISSING,
    # 定数 — CAP
    CAP_NOT_FOUND,
    CAP_EXECUTION_ERROR,
    # 定数 — VAL
    VAL_EMPTY_VALUE,
    VAL_PATTERN_MISMATCH,
    VAL_PATH_TRAVERSAL,
    VAL_SYMLINK_DETECTED,
    VAL_ENTRYPOINT_INVALID,
    VAL_FILE_NOT_FOUND,
    VAL_BODY_TOO_LARGE,
    # 定数 — SYS
    SYS_INTERNAL_ERROR,
    SYS_CONFIG_ERROR,
    SYS_DIRECTORY_NOT_FOUND,
)


# ======================================================================
# RumiError クラス
# ======================================================================


class TestRumiErrorCreation:
    """RumiError の生成テスト。"""

    def test_basic_creation(self):
        err = RumiError(code="RUMI-SYS-001", message="Something went wrong")
        assert err.code == "RUMI-SYS-001"
        assert err.message == "Something went wrong"
        assert err.details is None
        assert err.suggestion is None

    def test_with_details(self):
        details = {"key": "value", "count": 42}
        err = RumiError(code="RUMI-VAL-001", message="Invalid", details=details)
        assert err.details == {"key": "value", "count": 42}

    def test_with_suggestion(self):
        err = RumiError(
            code="RUMI-AUTH-001",
            message="Token invalid",
            suggestion="Try refreshing.",
        )
        assert err.suggestion == "Try refreshing."

    def test_all_fields(self):
        err = RumiError(
            code="RUMI-NET-001",
            message="Connection failed",
            details={"host": "example.com"},
            suggestion="Check network.",
        )
        assert err.code == "RUMI-NET-001"
        assert err.message == "Connection failed"
        assert err.details == {"host": "example.com"}
        assert err.suggestion == "Check network."

    def test_is_exception_subclass(self):
        err = RumiError(code="RUMI-SYS-001", message="Error")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(RumiError) as exc_info:
            raise RumiError(code="RUMI-SYS-001", message="boom")
        assert exc_info.value.code == "RUMI-SYS-001"
        assert exc_info.value.message == "boom"


class TestRumiErrorStr:
    """RumiError.__str__ / __repr__ テスト。"""

    def test_str_format(self):
        err = RumiError(code="RUMI-PACK-001", message="Invalid pack_id")
        assert str(err) == "RUMI-PACK-001: Invalid pack_id"

    def test_repr_basic(self):
        err = RumiError(code="RUMI-SYS-001", message="Error")
        r = repr(err)
        assert r.startswith("RumiError(")
        assert "RUMI-SYS-001" in r
        assert "'Error'" in r

    def test_repr_with_all_fields(self):
        err = RumiError(
            code="RUMI-SYS-001",
            message="Error",
            details={"k": "v"},
            suggestion="Fix it.",
        )
        r = repr(err)
        assert "details=" in r
        assert "suggestion=" in r


class TestRumiErrorToDict:
    """RumiError.to_dict テスト。"""

    def test_basic(self):
        err = RumiError(code="RUMI-VAL-001", message="empty")
        d = err.to_dict()
        assert d == {"code": "RUMI-VAL-001", "message": "empty"}
        assert "details" not in d
        assert "suggestion" not in d

    def test_with_details(self):
        err = RumiError(
            code="RUMI-VAL-002", message="bad", details={"field": "name"}
        )
        d = err.to_dict()
        assert d["details"] == {"field": "name"}

    def test_with_suggestion(self):
        err = RumiError(
            code="RUMI-VAL-003", message="traversal", suggestion="Fix path."
        )
        d = err.to_dict()
        assert d["suggestion"] == "Fix path."

    def test_with_all_fields(self):
        err = RumiError(
            code="RUMI-SYS-002",
            message="Config error",
            details={"file": "config.yaml"},
            suggestion="Check config.",
        )
        d = err.to_dict()
        assert d["code"] == "RUMI-SYS-002"
        assert d["message"] == "Config error"
        assert d["details"] == {"file": "config.yaml"}
        assert d["suggestion"] == "Check config."

    def test_json_serializable(self):
        err = RumiError(
            code="RUMI-SYS-001",
            message="Error",
            details={"count": 42, "items": ["a", "b"]},
            suggestion="Retry.",
        )
        serialized = json.dumps(err.to_dict())
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["code"] == "RUMI-SYS-001"
        assert parsed["details"]["count"] == 42


# ======================================================================
# ErrorCode データクラス
# ======================================================================


class TestErrorCode:
    """ErrorCode データクラスのテスト。"""

    def test_basic_creation(self):
        ec = ErrorCode(code="RUMI-SYS-001", template="Error: {reason}")
        assert ec.code == "RUMI-SYS-001"
        assert ec.template == "Error: {reason}"
        assert ec.suggestion is None
        assert ec.category is None

    def test_with_all_fields(self):
        ec = ErrorCode(
            code="RUMI-AUTH-001",
            template="Token invalid",
            suggestion="Refresh.",
            category=ErrorCategory.AUTH,
        )
        assert ec.suggestion == "Refresh."
        assert ec.category == ErrorCategory.AUTH

    def test_invalid_code_format_raises(self):
        with pytest.raises(ValueError, match="Invalid error code format"):
            ErrorCode(code="BAD-CODE", template="bad")

    def test_invalid_code_short_category(self):
        with pytest.raises(ValueError):
            ErrorCode(code="RUMI-A-001", template="bad")

    def test_invalid_code_lowercase(self):
        with pytest.raises(ValueError):
            ErrorCode(code="RUMI-auth-001", template="bad")

    def test_invalid_code_missing_number(self):
        with pytest.raises(ValueError):
            ErrorCode(code="RUMI-AUTH-01", template="bad")

    def test_frozen_immutable(self):
        ec = ErrorCode(code="RUMI-SYS-001", template="test")
        with pytest.raises(AttributeError):
            ec.code = "RUMI-SYS-002"  # type: ignore


# ======================================================================
# エラーコード定数の整合性
# ======================================================================


class TestErrorConstants:
    """エラーコード定数の整合性テスト。"""

    def test_all_codes_valid_format(self):
        all_codes = get_all_error_codes()
        assert len(all_codes) > 0
        for code_str, ec in all_codes.items():
            assert ERROR_CODE_PATTERN.match(code_str), f"Invalid format: {code_str}"
            assert ec.code == code_str

    def test_no_duplicate_codes(self):
        all_codes = get_all_error_codes()
        codes = list(all_codes.keys())
        assert len(codes) == len(set(codes))

    def test_expected_total_count(self):
        all_codes = get_all_error_codes()
        # AUTH(3) + NET(3) + FLOW(3) + PACK(4) + CAP(2) + VAL(7) + SYS(3) = 25
        assert len(all_codes) == 25

    def test_all_categories_have_codes(self):
        all_codes = get_all_error_codes()
        categories_with_codes = set()
        for ec in all_codes.values():
            if ec.category is not None:
                categories_with_codes.add(ec.category)
        for cat in ErrorCategory:
            assert cat in categories_with_codes, f"No codes for {cat.value}"

    def test_all_constants_have_templates(self):
        all_codes = get_all_error_codes()
        for code_str, ec in all_codes.items():
            assert ec.template, f"Empty template for {code_str}"

    def test_all_constants_have_suggestions(self):
        all_codes = get_all_error_codes()
        for code_str, ec in all_codes.items():
            assert ec.suggestion, f"Empty suggestion for {code_str}"

    def test_all_constants_have_category(self):
        all_codes = get_all_error_codes()
        for code_str, ec in all_codes.items():
            assert ec.category is not None, f"No category for {code_str}"

    def test_get_error_code_found(self):
        ec = get_error_code("RUMI-AUTH-001")
        assert ec is not None
        assert ec is AUTH_TOKEN_INVALID

    def test_get_error_code_not_found(self):
        ec = get_error_code("RUMI-XXX-999")
        assert ec is None

    def test_auth_codes(self):
        assert AUTH_TOKEN_INVALID.code == "RUMI-AUTH-001"
        assert AUTH_TOKEN_EXPIRED.code == "RUMI-AUTH-002"
        assert AUTH_PERMISSION_DENIED.code == "RUMI-AUTH-003"

    def test_net_codes(self):
        assert NET_CONNECTION_FAILED.code == "RUMI-NET-001"
        assert NET_REQUEST_TIMEOUT.code == "RUMI-NET-002"
        assert NET_PROXY_ERROR.code == "RUMI-NET-003"

    def test_flow_codes(self):
        assert FLOW_NOT_FOUND.code == "RUMI-FLOW-001"
        assert FLOW_EXECUTION_ERROR.code == "RUMI-FLOW-002"
        assert FLOW_STEP_FAILED.code == "RUMI-FLOW-003"

    def test_pack_codes(self):
        assert PACK_ID_INVALID.code == "RUMI-PACK-001"
        assert PACK_ECOSYSTEM_INVALID.code == "RUMI-PACK-002"
        assert PACK_ID_MISMATCH.code == "RUMI-PACK-003"
        assert PACK_CONNECTIVITY_MISSING.code == "RUMI-PACK-004"

    def test_val_codes(self):
        assert VAL_EMPTY_VALUE.code == "RUMI-VAL-001"
        assert VAL_PATTERN_MISMATCH.code == "RUMI-VAL-002"
        assert VAL_PATH_TRAVERSAL.code == "RUMI-VAL-003"
        assert VAL_SYMLINK_DETECTED.code == "RUMI-VAL-004"
        assert VAL_ENTRYPOINT_INVALID.code == "RUMI-VAL-005"
        assert VAL_FILE_NOT_FOUND.code == "RUMI-VAL-006"
        assert VAL_BODY_TOO_LARGE.code == "RUMI-VAL-007"

    def test_sys_codes(self):
        assert SYS_INTERNAL_ERROR.code == "RUMI-SYS-001"
        assert SYS_CONFIG_ERROR.code == "RUMI-SYS-002"
        assert SYS_DIRECTORY_NOT_FOUND.code == "RUMI-SYS-003"

    def test_cap_codes(self):
        assert CAP_NOT_FOUND.code == "RUMI-CAP-001"
        assert CAP_EXECUTION_ERROR.code == "RUMI-CAP-002"


# ======================================================================
# format_error ヘルパー
# ======================================================================


class TestFormatError:
    """format_error ヘルパーのテスト。"""

    def test_basic_no_params(self):
        err = format_error(AUTH_TOKEN_INVALID)
        assert isinstance(err, RumiError)
        assert err.code == "RUMI-AUTH-001"
        assert err.message == "Authentication token is invalid"

    def test_template_expansion(self):
        err = format_error(AUTH_PERMISSION_DENIED, reason="admin required")
        assert err.code == "RUMI-AUTH-003"
        assert err.message == "Permission denied: admin required"

    def test_with_details(self):
        err = format_error(
            SYS_INTERNAL_ERROR,
            reason="disk full",
            details={"disk": "/dev/sda1"},
        )
        assert err.details == {"disk": "/dev/sda1"}
        assert "disk full" in err.message

    def test_default_suggestion_used(self):
        err = format_error(AUTH_TOKEN_INVALID)
        assert err.suggestion == AUTH_TOKEN_INVALID.suggestion

    def test_suggestion_override(self):
        err = format_error(AUTH_TOKEN_INVALID, suggestion="Contact admin.")
        assert err.suggestion == "Contact admin."

    def test_missing_template_param_graceful(self):
        err = format_error(NET_CONNECTION_FAILED)  # missing 'target'
        assert isinstance(err, RumiError)
        assert err.code == "RUMI-NET-001"
        assert "missing parameter" in err.message

    def test_complex_template_val_pattern(self):
        err = format_error(
            VAL_PATTERN_MISMATCH,
            field_name="slug",
            pattern="[a-z]+",
            value="BAD!",
        )
        assert "slug" in err.message
        assert "[a-z]+" in err.message
        assert "'BAD!'" in err.message  # !r adds quotes

    def test_pack_id_invalid_literal_braces(self):
        err = format_error(PACK_ID_INVALID, pack_id="bad pack!")
        assert "'bad pack!'" in err.message  # !r
        assert "{1,64}" in err.message  # literal braces from {{1,64}}

    def test_pack_connectivity_template(self):
        err = format_error(
            PACK_CONNECTIVITY_MISSING,
            pack_id="pack_a",
            ref_pack_id="pack_b",
        )
        assert "pack_a" in err.message
        assert "pack_b" in err.message
        assert "${ctx}" in err.message  # literal from ${{ctx}}

    def test_multi_param_template(self):
        err = format_error(
            FLOW_STEP_FAILED,
            step="step_3",
            flow_id="main_flow",
            reason="timeout",
        )
        assert "step_3" in err.message
        assert "main_flow" in err.message
        assert "timeout" in err.message

    def test_returned_type(self):
        err = format_error(SYS_DIRECTORY_NOT_FOUND, directory="/tmp/missing")
        assert type(err) is RumiError

    def test_to_dict_after_format(self):
        err = format_error(
            VAL_BODY_TOO_LARGE,
            size=20_000_000,
            max_size=10_485_760,
            details={"endpoint": "/upload"},
        )
        d = err.to_dict()
        assert d["code"] == "RUMI-VAL-007"
        assert "20000000" in d["message"]
        assert d["details"] == {"endpoint": "/upload"}
        assert d["suggestion"] == VAL_BODY_TOO_LARGE.suggestion


# ======================================================================
# ErrorCategory enum
# ======================================================================


class TestErrorCategory:
    """ErrorCategory enum テスト。"""

    def test_all_categories_exist(self):
        expected = {"AUTH", "NET", "FLOW", "PACK", "CAP", "VAL", "SYS"}
        actual = {cat.value for cat in ErrorCategory}
        assert actual == expected

    def test_category_count(self):
        assert len(ErrorCategory) == 7

    def test_category_values(self):
        assert ErrorCategory.AUTH.value == "AUTH"
        assert ErrorCategory.NET.value == "NET"
        assert ErrorCategory.FLOW.value == "FLOW"
        assert ErrorCategory.PACK.value == "PACK"
        assert ErrorCategory.CAP.value == "CAP"
        assert ErrorCategory.VAL.value == "VAL"
        assert ErrorCategory.SYS.value == "SYS"


# ======================================================================
# ERROR_CODE_PATTERN 正規表現
# ======================================================================


class TestErrorCodePattern:
    """ERROR_CODE_PATTERN 正規表現のテスト。"""

    @pytest.mark.parametrize(
        "code",
        [
            "RUMI-AUTH-001",
            "RUMI-NET-999",
            "RUMI-SYS-000",
            "RUMI-ABCDE-123",  # 5文字カテゴリ
            "RUMI-AB-456",      # 2文字カテゴリ
        ],
    )
    def test_valid_codes(self, code):
        assert ERROR_CODE_PATTERN.match(code), f"Should match: {code}"

    @pytest.mark.parametrize(
        "code",
        [
            "RUMI-A-001",        # 1文字カテゴリ（短すぎ）
            "RUMI-ABCDEF-001",   # 6文字カテゴリ（長すぎ）
            "RUMI-auth-001",     # 小文字
            "RUMI-AUTH-01",      # 2桁番号
            "RUMI-AUTH-1000",    # 4桁番号
            "AUTH-001",          # RUMI- なし
            "rumi-AUTH-001",     # rumi 小文字
            "",                  # 空文字
        ],
    )
    def test_invalid_codes(self, code):
        assert not ERROR_CODE_PATTERN.match(code), f"Should not match: {code}"
