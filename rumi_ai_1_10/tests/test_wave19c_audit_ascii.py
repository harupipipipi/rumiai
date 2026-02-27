"""
W19-C / VULN-H05: ensure_ascii=True でログインジェクションを防止するテスト
"""
import importlib.util
import json
import pathlib
import sys

# ---- AuditEntry を単独ロード (パッケージ __init__.py を回避) ----
_MOD_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "core_runtime" / "audit_logger.py"
)
_spec = importlib.util.spec_from_file_location(
    "audit_logger_isolated",
    str(_MOD_PATH),
    submodule_search_locations=[],
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
AuditEntry = _mod.AuditEntry


def _make_entry(**overrides):
    defaults = dict(
        ts="2026-01-01T00:00:00Z",
        category="security",
        severity="info",
        action="test_action",
        success=True,
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


def test_non_ascii_chars_are_escaped():
    """非ASCII文字が \\uXXXX にエスケープされること"""
    entry = _make_entry(owner_pack="テストパック")
    j = entry.to_json()
    assert "テスト" not in j, f"Non-ASCII must be escaped: {j!r}"
    assert "\\u" in j
    parsed = json.loads(j)
    assert parsed["owner_pack"] == "テストパック"


def test_newline_injection_prevented():
    """改行を含む pack_id でログインジェクションが防止されること"""
    malicious = 'evil\n{"injected": true}'
    entry = _make_entry(owner_pack=malicious)
    j = entry.to_json()
    assert "\n" not in j, f"Literal newline in output: {j!r}"
    assert "\r" not in j
    parsed = json.loads(j)
    assert parsed["owner_pack"] == malicious


def test_unicode_line_separator_escaped():
    """U+2028 LINE SEPARATOR が \\u2028 にエスケープされること"""
    entry = _make_entry(owner_pack="before\u2028after")
    j = entry.to_json()
    assert "\u2028" not in j, f"U+2028 must be escaped: {j!r}"
    assert "\\u2028" in j
    parsed = json.loads(j)
    assert parsed["owner_pack"] == "before\u2028after"


def test_ascii_input_unchanged():
    """通常の ASCII 入力で既存動作が維持されること"""
    entry = _make_entry(
        owner_pack="normal_pack_123",
        flow_id="flow-abc",
        details={"key": "value", "count": 42},
    )
    j = entry.to_json()
    parsed = json.loads(j)
    assert parsed["owner_pack"] == "normal_pack_123"
    assert parsed["flow_id"] == "flow-abc"
    assert parsed["success"] is True
    assert parsed["details"]["key"] == "value"
    assert parsed["details"]["count"] == 42


def test_unicode_paragraph_separator_escaped():
    """U+2029 PARAGRAPH SEPARATOR もエスケープされること"""
    entry = _make_entry(error="msg\u2029end")
    j = entry.to_json()
    assert "\u2029" not in j, f"U+2029 must be escaped: {j!r}"
    assert "\\u2029" in j
    parsed = json.loads(j)
    assert parsed["error"] == "msg\u2029end"
