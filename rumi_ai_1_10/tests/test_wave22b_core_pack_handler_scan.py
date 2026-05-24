"""
test_wave22b_core_pack_handler_scan.py - W22-B: core_pack function scan tests

Phase D removes CapabilityHandlerRegistry. These tests keep the old core-pack
scan coverage, but assert the post-Phase-D FunctionRegistry contract instead:
functions/<function_id>/manifest.json is scanned into FunctionRegistry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core_runtime.function_registry import FunctionRegistry


@dataclass
class _ScanResult:
    success: bool = True
    functions_loaded: int = 0
    errors: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)


def _make_function(
    base_dir: Path,
    function_id: str,
    permission_id: str,
    *,
    manifest_extra: dict | None = None,
) -> Path:
    """manifest.json + main.py を base_dir/function_id/ に作成する。"""
    function_dir = base_dir / function_id
    function_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "function_id": function_id,
        "permission_id": permission_id,
        "vocab_aliases": [permission_id],
        "entrypoint": "main.py:run",
        "description": f"Test function {function_id}",
        "risk": "low",
        "is_builtin": True,
        "calling_convention": "subprocess",
        "grant_config": {},
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    (function_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (function_dir / "main.py").write_text(
        "def run(context, args):\n    return args\n", encoding="utf-8"
    )
    return function_dir


def _make_core_pack_structure(
    core_pack_base: Path,
    pack_name: str,
    function_id: str,
    permission_id: str,
) -> Path:
    """core_pack ディレクトリ構造を作成し functions dir を返す。"""
    functions_dir = core_pack_base / pack_name / "functions"
    functions_dir.mkdir(parents=True, exist_ok=True)
    _make_function(functions_dir, function_id, permission_id)
    return functions_dir


def _load_function_dirs(
    registry: FunctionRegistry,
    sources: list[tuple[str, Path]],
) -> _ScanResult:
    """functions/ ディレクトリ群を FunctionRegistry に登録するテスト用 scanner。"""
    result = _ScanResult()

    for pack_id, functions_dir in sources:
        if not functions_dir.exists():
            continue
        for function_dir in sorted(functions_dir.iterdir(), key=lambda p: p.name):
            if not function_dir.is_dir():
                continue
            manifest_path = function_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                result.errors.append(
                    {"function_dir": str(function_dir), "error": f"Invalid manifest.json: {exc}"}
                )
                continue

            function_id = manifest.get("function_id") or function_dir.name
            manifest.setdefault("function_id", function_id)
            manifest.setdefault("is_builtin", pack_id.startswith("core_") or pack_id == "kernel")
            permission_id = manifest.get("permission_id")
            if permission_id and registry.get_by_permission_id(permission_id) is not None:
                result.success = False
                result.duplicates.append(
                    {"permission_id": permission_id, "function_dir": str(function_dir)}
                )
                continue

            if registry.register(
                pack_id=pack_id,
                function_id=function_id,
                manifest=manifest,
                function_dir=function_dir,
            ):
                result.functions_loaded += 1

    return result


def _make_registry(
    *,
    user_functions: tuple[str, Path] | None = None,
    builtin_dir: Path | None = None,
    core_pack_dirs: list[tuple[str, Path]] | None = None,
) -> tuple[FunctionRegistry, _ScanResult]:
    """テスト用 FunctionRegistry を組み立て、指定 source を登録する。"""
    registry = FunctionRegistry()
    sources: list[tuple[str, Path]] = []
    if user_functions:
        sources.append(user_functions)
    if builtin_dir:
        sources.append(("kernel", builtin_dir))
    if core_pack_dirs:
        sources.extend(core_pack_dirs)
    return registry, _load_function_dirs(registry, sources)


class TestCorePackFunctionScan:
    """core_pack function スキャンの検証 (W22-B / Phase D)"""

    def test_core_pack_function_scanned(self, tmp_path: Path) -> None:
        """core_pack に manifest.json がある場合 FunctionRegistry に登録される。"""
        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_test", "test_run", "test.run",
        )
        reg, result = _make_registry(core_pack_dirs=[("core_test", functions_dir)])
        assert result.success is True
        assert result.functions_loaded == 1
        assert reg.get_by_permission_id("test.run") is not None

    def test_core_pack_function_is_builtin(self, tmp_path: Path) -> None:
        """スキャンされた core_pack function は is_builtin=True。"""
        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_test", "test_run", "test.run",
        )
        reg, _ = _make_registry(core_pack_dirs=[("core_test", functions_dir)])
        entry = reg.get_by_permission_id("test.run")
        assert entry is not None
        assert entry.is_builtin is True

    def test_core_pack_function_permission_id_registered(
        self, tmp_path: Path,
    ) -> None:
        """core_pack function の permission_id が FunctionRegistry に入る。"""
        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_docker", "docker_run", "docker.run",
        )
        reg, _ = _make_registry(core_pack_dirs=[("core_docker", functions_dir)])
        assert reg.get_by_permission_id("docker.run") is not None

    def test_core_pack_dir_not_exists_no_error(
        self, tmp_path: Path,
    ) -> None:
        """core_pack ディレクトリが存在しない場合でもエラーにならない。"""
        reg, result = _make_registry(core_pack_dirs=[("core_missing", tmp_path / "missing")])
        assert result.success is True
        assert result.functions_loaded == 0
        assert reg.count() == 0

    def test_builtin_and_core_pack_both_loaded(
        self, tmp_path: Path,
    ) -> None:
        """built-in function と core_pack function が両方ロードされる。"""
        builtin_dir = tmp_path / "builtin"
        _make_function(builtin_dir, "kernel_info", "kernel.info")

        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "cp_run", "cp.run",
        )
        reg, result = _make_registry(
            builtin_dir=builtin_dir,
            core_pack_dirs=[("core_t", functions_dir)],
        )
        assert result.success is True
        assert result.functions_loaded == 2
        assert reg.get_by_permission_id("kernel.info") is not None
        assert reg.get_by_permission_id("cp.run") is not None

    def test_user_and_core_pack_both_loaded(
        self, tmp_path: Path,
    ) -> None:
        """user function と core_pack function が両方ロードされる。"""
        user_dir = tmp_path / "user_functions"
        _make_function(user_dir, "user_run", "user.run", manifest_extra={"is_builtin": False})

        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "cp_run", "cp.run",
        )
        reg, result = _make_registry(
            user_functions=("user_pack", user_dir),
            core_pack_dirs=[("core_t", functions_dir)],
        )
        assert result.success is True
        assert result.functions_loaded == 2
        assert reg.get_by_permission_id("user.run") is not None
        assert reg.get_by_permission_id("cp.run") is not None

    def test_core_pack_user_same_permission_id_duplicate(
        self, tmp_path: Path,
    ) -> None:
        """core_pack と user で同じ permission_id があると重複エラー。"""
        user_dir = tmp_path / "user_functions"
        _make_function(user_dir, "user_dup", "shared.run", manifest_extra={"is_builtin": False})

        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "core_dup", "shared.run",
        )
        _, result = _make_registry(
            user_functions=("user_pack", user_dir),
            core_pack_dirs=[("core_t", functions_dir)],
        )
        assert result.success is False
        dup_pids = [d["permission_id"] for d in result.duplicates]
        assert "shared.run" in dup_pids

    def test_invalid_manifest_json_skipped(
        self, tmp_path: Path,
    ) -> None:
        """manifest.json が不正な場合、その function だけスキップされる。"""
        functions_dir = tmp_path / "cp" / "core_t" / "functions"
        functions_dir.mkdir(parents=True)
        _make_function(functions_dir, "good_run", "good.run")

        bad_dir = functions_dir / "bad_run"
        bad_dir.mkdir()
        (bad_dir / "manifest.json").write_text("{invalid", encoding="utf-8")
        (bad_dir / "main.py").write_text(
            "def run(context, args): return args\n", encoding="utf-8"
        )

        reg, result = _make_registry(core_pack_dirs=[("core_t", functions_dir)])
        assert result.success is True
        assert result.functions_loaded == 1
        assert reg.get_by_permission_id("good.run") is not None
        assert len(result.errors) >= 1

    def test_empty_core_pack_dir_no_error(
        self, tmp_path: Path,
    ) -> None:
        """空の functions ディレクトリでエラーにならない。"""
        empty_dir = tmp_path / "cp" / "core_empty" / "functions"
        empty_dir.mkdir(parents=True)
        reg, result = _make_registry(core_pack_dirs=[("core_empty", empty_dir)])
        assert result.success is True
        assert result.functions_loaded == 0
        assert reg.count() == 0

    def test_multiple_core_packs_all_scanned(
        self, tmp_path: Path,
    ) -> None:
        """複数 core_pack の function が全てスキャンされる。"""
        cp_base = tmp_path / "cp"
        d1 = _make_core_pack_structure(cp_base, "core_a", "run_a", "a.run")
        d2 = _make_core_pack_structure(cp_base, "core_b", "run_b", "b.run")
        reg, result = _make_registry(core_pack_dirs=[("core_a", d1), ("core_b", d2)])
        assert result.success is True
        assert result.functions_loaded == 2
        assert reg.get_by_permission_id("a.run") is not None
        assert reg.get_by_permission_id("b.run") is not None

    def test_core_pack_function_dir_and_main_py_path(
        self, tmp_path: Path,
    ) -> None:
        """function_dir / main_py_path が正しく設定される。"""
        functions_dir = _make_core_pack_structure(
            tmp_path / "cp", "core_t", "my_run", "my.run",
        )
        reg, _ = _make_registry(core_pack_dirs=[("core_t", functions_dir)])
        entry = reg.get_by_permission_id("my.run")
        assert entry is not None
        assert entry.function_dir is not None
        assert entry.main_py_path is not None
        assert entry.main_py_path.name == "main.py"
        assert entry.function_dir.name == "my_run"

    def test_manifest_missing_function_id_uses_directory_name(
        self, tmp_path: Path,
    ) -> None:
        """function_id が無い manifest はディレクトリ名で登録される。"""
        functions_dir = tmp_path / "cp" / "core_t" / "functions"
        function_dir = functions_dir / "fallback_run"
        function_dir.mkdir(parents=True)
        (function_dir / "manifest.json").write_text(
            json.dumps({
                "permission_id": "fallback.run",
                "vocab_aliases": ["fallback.run"],
                "entrypoint": "main.py:run",
            }),
            encoding="utf-8",
        )
        (function_dir / "main.py").write_text(
            "def run(context, args): return args\n", encoding="utf-8"
        )

        reg, result = _make_registry(core_pack_dirs=[("core_t", functions_dir)])
        assert result.success is True
        assert result.functions_loaded == 1
        entry = reg.get("core_t:fallback_run")
        assert entry is not None
        assert entry.permission_id == "fallback.run"
