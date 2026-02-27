"""
W19-C / VULN-H05: ensure_ascii=True でログインジェクションを防止するテスト

AuditEntry.to_json() が ensure_ascii=True を使用していることを検証する。
core_runtime パッケージ全体の __init__.py を経由しないよう importlib で単独ロードする。
"""

import importlib.util
import json
import pathlib
import sys

# ---------- AuditEntry を単独ロード (パッケージ __init__.py を回避) ----------
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


# ---------- ヘルパー ----------
def _make_entry(**overrides):
    """最小限の AuditEntry を生成する。"""
    defaults = dict(
        ts="2026-01-01T00:00:00Z",
        category="security",
        severity="info",
        action="test_action",
        success=True,
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


# ---------- テスト ----------

def test_non_ascii_chars_are_escaped():
    """非ASCII文字（日本語）が \\uXXXX にエスケープされること。"""
    entry = _make_entry(owner_pack="テストパック")
    j = entry.to_json()

    # 生の日本語文字列が含まれていないこと
    assert "テスト" not in j, f"Non-ASCII chars must be escaped: {j!r}"
    # \\uXXXX 形式が存在すること
    assert "\\u" in j, f"Expected unicode escapes in output: {j!r}"
    # デシリアライズして元の文字列に戻ること
    parsed = json.loads(j)
    assert parsed["owner_pack"] == "テストパック"


def test_newline_injection_prevented():
    """改行を含む pack_id でログインジェクションが防止されること。"""
    malicious = 'evil\n{"injected": true}'
    entry = _make_entry(owner_pack=malicious)
    j = entry.to_json()

    # 出力文字列にリテラル改行が含まれないこと（= 1 行で完結）
    assert "\n" not in j, f"Literal newline must not appear in JSON line: {j!r}"
    assert "\r" not in j, f"Literal CR must not appear in JSON line: {j!r}"

    # デシリアライズして元の文字列に戻ること
    parsed = json.loads(j)
    assert parsed["owner_pack"] == malicious


def test_unicode_line_separator_escaped():
    """U+2028 LINE SEPARATOR が \\u2028 にエスケープされること。"""
    entry = _make_entry(owner_pack="before\u2028after")
    j = entry.to_json()

    # 生の U+2028 がバイト列に含まれないこと
    assert "\u2028" not in j, f"U+2028 must be escaped: {j!r}"
    # エスケープ形式で含まれていること
    assert "\\u2028" in j, f"Expected \\\\u2028 in output: {j!r}"

    # デシリアライズして元に戻ること
    parsed = json.loads(j)
    assert parsed["owner_pack"] == "before\u2028after"


def test_ascii_input_unchanged():
    """通常の ASCII 入力で既存動作が維持されること。"""
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
    """U+2029 PARAGRAPH SEPARATOR もエスケープされること（追加安全策）。"""
    entry = _make_entry(error="msg\u2029end")
    j = entry.to_json()

    assert "\u2029" not in j, f"U+2029 must be escaped: {j!r}"
    assert "\\u2029" in j, f"Expected \\\\u2029 in output: {j!r}"

    parsed = json.loads(j)
    assert parsed["error"] == "msg\u2029end"
