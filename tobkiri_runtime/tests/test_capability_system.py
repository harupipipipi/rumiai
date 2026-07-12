"""
test_capability_system.py - Capability システムの統合テスト (unittest)

テスト観点:
- ダミーハンドラーの登録と実行
- Trust あり/なしで allow/deny
- Grant あり/なしで allow/deny
- principal_id 違いでの拒否
- タイムアウト
- 重複 permission_id の起動失敗
- 監査ログ記録
- HMAC 署名検証
- payload の principal_id は無視される（UDS由来が優先）
- E2E プロキシテスト
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path

# テスト対象をインポートできるようにパスを追加
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _compute_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _write_lp(sock, data: dict):
    """length-prefix JSON を書き込む"""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def _read_lp(sock, max_size=4 * 1024 * 1024) -> dict:
    """length-prefix JSON を読み取る"""
    ld = b""
    while len(ld) < 4:
        c = sock.recv(4 - len(ld))
        if not c:
            raise ConnectionError("closed")
        ld += c
    length = struct.unpack(">I", ld)[0]
    if length > max_size:
        raise ValueError("too large")
    d = b""
    while len(d) < length:
        c = sock.recv(min(length - len(d), 65536))
        if not c:
            raise ConnectionError("closed")
        d += c
    return json.loads(d.decode("utf-8"))


# =============================================================================
# ハンドラーレジストリのテスト
# =============================================================================


class TestCapabilityHandlerRegistry(unittest.TestCase):
    """ハンドラーレジストリのテスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_cap_")
        self.handlers_dir = Path(self.tmpdir) / "handlers"
        self.handlers_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_handler(self, slug, handler_id, permission_id, code=None):
        """テスト用ハンドラーを作成"""
        d = self.handlers_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "handler.json").write_text(
            json.dumps({
                "handler_id": handler_id,
                "permission_id": permission_id,
                "entrypoint": "handler.py:execute",
                "description": f"Test handler for {permission_id}",
            }),
            encoding="utf-8",
        )
        if code is None:
            code = 'def execute(context, args): return {"echo": args}\n'
        (d / "handler.py").write_text(code, encoding="utf-8")
        return d

    def test_load_single_handler(self):
        """単一ハンドラーのロード"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("echo", "test.echo.v1", "test.echo")
        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 1)
        h = reg.get_by_permission_id("test.echo")
        self.assertIsNotNone(h)
        self.assertEqual(h.handler_id, "test.echo.v1")
        self.assertEqual(h.permission_id, "test.echo")
        self.assertIsNotNone(h.handler_py_sha256)
        self.assertTrue(len(h.handler_py_sha256) == 64)

    def test_load_multiple_handlers(self):
        """複数ハンドラーのロード（異なる permission_id）"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("echo", "test.echo.v1", "test.echo")
        self._create_handler("read", "test.read.v1", "fs.read")
        self._create_handler("write", "test.write.v1", "fs.write")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 3)
        self.assertIsNotNone(reg.get_by_permission_id("test.echo"))
        self.assertIsNotNone(reg.get_by_permission_id("fs.read"))
        self.assertIsNotNone(reg.get_by_permission_id("fs.write"))

    def test_duplicate_permission_id_fails(self):
        """重複 permission_id は起動失敗"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("handler_a", "handler.a.v1", "dup.perm")
        self._create_handler("handler_b", "handler.b.v1", "dup.perm")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertFalse(r.success)
        self.assertTrue(len(r.duplicates) > 0)
        self.assertEqual(r.duplicates[0]["permission_id"], "dup.perm")
        self.assertEqual(r.duplicates[0]["handler_count"], 2)

        # 重複した permission_id のハンドラーは登録されない
        self.assertIsNone(reg.get_by_permission_id("dup.perm"))
        self.assertFalse(reg.is_loaded())

    def test_duplicate_handler_id_error(self):
        """重複 handler_id はエラーとして記録"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("dir_a", "same.id.v1", "perm.a")
        self._create_handler("dir_b", "same.id.v1", "perm.b")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        # handler_id 重複はエラーだが、permission_id の重複ではないので success になりうる
        # 2つ目の handler_id がスキップされ、1つだけロードされる
        self.assertTrue(len(r.errors) > 0)
        dup_errors = [e for e in r.errors if "Duplicate handler_id" in e.get("error", "")]
        self.assertTrue(len(dup_errors) > 0)

    def test_missing_handler_py(self):
        """handler.py が無い場合はエラー"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        d = self.handlers_dir / "broken"
        d.mkdir(parents=True)
        (d / "handler.json").write_text(
            json.dumps({
                "handler_id": "broken.v1",
                "permission_id": "broken.perm",
                "entrypoint": "handler.py:execute",
            }),
            encoding="utf-8",
        )
        # handler.py を作らない

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)  # 壊れたのだけスキップ、全体は成功
        self.assertEqual(r.handlers_loaded, 0)
        self.assertTrue(len(r.errors) > 0)

    def test_missing_handler_json(self):
        """handler.json が無いディレクトリはスキップ"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        d = self.handlers_dir / "no_json"
        d.mkdir(parents=True)
        (d / "handler.py").write_text("def execute(c, a): pass\n", encoding="utf-8")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 0)
        self.assertTrue(len(r.errors) > 0)

    def test_invalid_entrypoint_format(self):
        """entrypoint が 'file:func' 形式でない場合はエラー"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        d = self.handlers_dir / "bad_ep"
        d.mkdir(parents=True)
        (d / "handler.json").write_text(
            json.dumps({
                "handler_id": "bad.v1",
                "permission_id": "bad.perm",
                "entrypoint": "no_colon_here",
            }),
            encoding="utf-8",
        )
        (d / "handler.py").write_text("def execute(c, a): pass\n", encoding="utf-8")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 0)
        self.assertTrue(len(r.errors) > 0)

    def test_empty_directory(self):
        """空ディレクトリではハンドラー0個で成功"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 0)
        self.assertEqual(len(r.errors), 0)
        self.assertEqual(len(r.duplicates), 0)

    def test_nonexistent_directory(self):
        """存在しないディレクトリでも成功（0個）"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        reg = CapabilityHandlerRegistry(str(Path(self.tmpdir) / "nonexistent"))
        r = reg.load_all()

        self.assertTrue(r.success)
        self.assertEqual(r.handlers_loaded, 0)

    def test_get_by_handler_id(self):
        """handler_id での取得"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("echo", "test.echo.v1", "test.echo")
        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        reg.load_all()

        h = reg.get_by_handler_id("test.echo.v1")
        self.assertIsNotNone(h)
        self.assertEqual(h.permission_id, "test.echo")

        self.assertIsNone(reg.get_by_handler_id("nonexistent"))

    def test_list_permission_ids(self):
        """permission_id 一覧"""
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry

        self._create_handler("a", "a.v1", "perm.a")
        self._create_handler("b", "b.v1", "perm.b")

        reg = CapabilityHandlerRegistry(str(self.handlers_dir))
        reg.load_all()

        ids = reg.list_permission_ids