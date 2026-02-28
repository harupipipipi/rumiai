"""
test_wave22b_core_pack_handler_scan.py - W22-B: core_pack handler scan tests

CapabilityHandlerRegistry.load_all() が core_pack 内の handler を
正しくスキャンすることを検証する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_runtime.capability_handler_registry import CapabilityHandlerRegistry


# ======================================================================
# ヘルパー
# ======================================================================

def _make_handler(
    base_dir: Path,
    slug: str,
    handler_id: str,
    permission_id: str,
) -> Path:
    """handler.json + handler.py を base_dir/slug/ に作成する。"""
    slug_dir = base_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    handler_json = {
        "handler_id": handler_id,
        "permission_id": permission_id,
        "entrypoint": "handler.py:execute",
        "description": f"Test handler {handler_id}",
        "risk": "low",
    }
    (slug_dir / "handler.json").write_text(
        json.dumps(handler_json), encoding="utf-8"
    )
    (slug_dir / "handler.py").write_text(
        "def execute(**kwargs):\n    pass\n", encoding="utf-8"
    )
    return slug_dir


def _make_core_pack_structure(
    core_pack_base: Path,
    pack_name: str,
    slug: str,
    handler_id: str,
    permission_id: str,
) -> Path:
    """core_pack ディレクトリ構造を作成し capability_handlers dir を返す。"""
    cap_dir = (
        core_pack_base / pack_name / "share" / "capability_handlers"
    )
    cap_dir.mkdir(parents=True, exist_ok=True)
    _make_handler(cap_dir, slug, handler_id, permission_id)
    return cap_dir


def _make_registry(
    tmp_path: Path,
    *,
    user_handlers: Path | None = None,
    builtin_dir: Path | None = None,
    core_pack_dirs: list[Path] | None = None,
) -> CapabilityHandlerRegistry:
    """テスト用 Registry を組み立てる。"""
    user_dir = user_handlers or (tmp_path / "user_handlers")
    user_dir.mkdir(parents=True, exist_ok=True)
    registry = CapabilityHandlerRegistry(handlers_dir=str(user_dir))
    registry._builtin_handlers_dir = builtin_dir
    registry._core_pack_handler_dirs = core_pack_dirs or []
    return registry


# ======================================================================
# テスト
# ======================================================================

class TestCorePackHandlerScan:
    """core_pack handler スキャンの検証 (W22-B)"""

    def test_core_pack_handler_scanned(self, tmp_path: Path) -> None:
        """core_pack に handler.json がある場合 load_all() でスキャンされる。"""
        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_test", "test_h",
            "core.test.run", "test.run",
        )
        reg = _make_registry(tmp_path, core_pack_dirs=[cap_dir])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 1
        assert reg.get_by_permission_id("test.run") is not None

    def test_core_pack_handler_is_builtin(self, tmp_path: Path) -> None:
        """スキャンされた core_pack handler は is_builtin=True。"""
        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_test", "test_h",
            "core.test.run", "test.run",
        )
        reg = _make_registry(tmp_path, core_pack_dirs=[cap_dir])
        reg.load_all()
        h = reg.get_by_permission_id("test.run")
        assert h is not None
        assert h.is_builtin is True

    def test_core_pack_handler_permission_id_registered(
        self, tmp_path: Path,
    ) -> None:
        """core_pack handler の permission_id が list_permission_ids に含まれる。"""
        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_docker", "docker_run",
            "core.docker.run", "docker.run",
        )
        reg = _make_registry(tmp_path, core_pack_dirs=[cap_dir])
        reg.load_all()
        assert "docker.run" in reg.list_permission_ids()

    def test_core_pack_dir_not_exists_no_error(
        self, tmp_path: Path,
    ) -> None:
        """core_pack ディレクトリが存在しない場合でもエラーにならない。"""
        reg = _make_registry(tmp_path, core_pack_dirs=[])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 0

    def test_builtin_and_core_pack_both_loaded(
        self, tmp_path: Path,
    ) -> None:
        """built-in handler と core_pack handler が両方ロードされる。"""
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        _make_handler(builtin_dir, "bi_h", "bi.handler", "bi.perm")

        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "cp_h",
            "cp.handler", "cp.perm",
        )
        reg = _make_registry(
            tmp_path,
            builtin_dir=builtin_dir,
            core_pack_dirs=[cap_dir],
        )
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 2
        assert reg.get_by_permission_id("bi.perm") is not None
        assert reg.get_by_permission_id("cp.perm") is not None

    def test_user_and_core_pack_both_loaded(
        self, tmp_path: Path,
    ) -> None:
        """user handler と core_pack handler が両方ロードされる。"""
        user_dir = tmp_path / "user_handlers"
        user_dir.mkdir()
        _make_handler(user_dir, "u_h", "u.handler", "u.perm")

        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "cp_h",
            "cp.handler", "cp.perm",
        )
        reg = _make_registry(
            tmp_path,
            user_handlers=user_dir,
            core_pack_dirs=[cap_dir],
        )
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 2
        assert reg.get_by_permission_id("u.perm") is not None
        assert reg.get_by_permission_id("cp.perm") is not None

    def test_core_pack_user_same_permission_id_duplicate(
        self, tmp_path: Path,
    ) -> None:
        """core_pack と user で同じ permission_id があると重複エラー。"""
        user_dir = tmp_path / "user_handlers"
        user_dir.mkdir()
        _make_handler(user_dir, "u_h", "u.dup", "shared.perm")

        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "cp_h",
            "cp.dup", "shared.perm",
        )
        reg = _make_registry(
            tmp_path,
            user_handlers=user_dir,
            core_pack_dirs=[cap_dir],
        )
        result = reg.load_all()
        assert result.success is False
        dup_pids = [d["permission_id"] for d in result.duplicates]
        assert "shared.perm" in dup_pids

    def test_invalid_handler_json_skipped(
        self, tmp_path: Path,
    ) -> None:
        """handler.json が不正な場合、その handler だけスキップされる。"""
        cp_base = (
            tmp_path / "cp" / "core_t" / "share" / "capability_handlers"
        )
        cp_base.mkdir(parents=True)
        _make_handler(cp_base, "good_h", "good.handler", "good.perm")

        bad_dir = cp_base / "bad_h"
        bad_dir.mkdir()
        (bad_dir / "handler.json").write_text(
            "{invalid", encoding="utf-8"
        )
        (bad_dir / "handler.py").write_text(
            "def execute(**kwargs): pass\n", encoding="utf-8"
        )

        reg = _make_registry(tmp_path, core_pack_dirs=[cp_base])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 1
        assert reg.get_by_permission_id("good.perm") is not None
        assert len(result.errors) >= 1

    def test_empty_core_pack_dir_no_error(
        self, tmp_path: Path,
    ) -> None:
        """空の capability_handlers ディレクトリでエラーにならない。"""
        empty_dir = (
            tmp_path / "cp" / "core_empty"
            / "share" / "capability_handlers"
        )
        empty_dir.mkdir(parents=True)
        reg = _make_registry(tmp_path, core_pack_dirs=[empty_dir])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 0

    def test_multiple_core_packs_all_scanned(
        self, tmp_path: Path,
    ) -> None:
        """複数 core_pack の handler が全てスキャンされる。"""
        cp_base = tmp_path / "cp"
        d1 = _make_core_pack_structure(
            cp_base, "core_a", "h_a", "a.handler", "a.perm",
        )
        d2 = _make_core_pack_structure(
            cp_base, "core_b", "h_b", "b.handler", "b.perm",
        )
        reg = _make_registry(tmp_path, core_pack_dirs=[d1, d2])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 2
        assert reg.get_by_permission_id("a.perm") is not None
        assert reg.get_by_permission_id("b.perm") is not None

    def test_core_pack_handler_dir_and_py_path(
        self, tmp_path: Path,
    ) -> None:
        """handler_dir / handler_py_path が正しく設定される。"""
        cap_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "my_h",
            "core.my.run", "my.run",
        )
        reg = _make_registry(tmp_path, core_pack_dirs=[cap_dir])
        reg.load_all()
        h = reg.get_by_permission_id("my.run")
        assert h is not None
        assert h.handler_dir is not None
        assert h.handler_py_path is not None
        assert h.handler_py_path.name == "handler.py"
        assert h.handler_dir.name == "my_h"

    def test_handler_json_missing_handler_id_skipped(
        self, tmp_path: Path,
    ) -> None:
        """handler_id が無い handler.json はスキップされる。"""
        cp_base = (
            tmp_path / "cp" / "core_t" / "share" / "capability_handlers"
        )
        cp_base.mkdir(parents=True)
        slug_dir = cp_base / "bad_h"
        slug_dir.mkdir()
        (slug_dir / "handler.json").write_text(
            json.dumps({
                "permission_id": "bad.perm",
                "entrypoint": "handler.py:execute",
            }),
            encoding="utf-8",
        )
        (slug_dir / "handler.py").write_text(
            "def execute(**kwargs): pass\n", encoding="utf-8"
        )

        reg = _make_registry(tmp_path, core_pack_dirs=[cp_base])
        result = reg.load_all()
        assert result.success is True
        assert result.handlers_loaded == 0
        assert len(result.errors) >= 1
