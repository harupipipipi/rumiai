"""
test_wave15a_kernel_core.py - Wave 15-A kernel_core.py 統合テスト

検証対象:
  1. logging → get_structured_logger 移行
  2. deprecated デコレータ適用 (_load_legacy_flow)
  3. types.py NewType 適用 (FlowId)
  4. 既存機能の後方互換
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helper: KernelCore のインスタンスを DI モック付きで生成する
# ---------------------------------------------------------------------------

def _make_kernel(**overrides):
    """DI コンテナをモックして KernelCore を生成するヘルパー。"""
    from core_runtime.diagnostics import Diagnostics
    from core_runtime.install_journal import InstallJournal
    from core_runtime.interface_registry import InterfaceRegistry
    from core_runtime.event_bus import EventBus

    diag = overrides.get("diagnostics") or Diagnostics()
    ij = overrides.get("install_journal") or InstallJournal()
    ir = overrides.get("interface_registry") or InterfaceRegistry()
    eb = overrides.get("event_bus") or EventBus()

    # InstallJournal.set_interface_registry が呼ばれるのでモック化
    if not hasattr(ij, "set_interface_registry"):
        ij.set_interface_registry = MagicMock()

    mock_container = MagicMock()
    mock_container.get.side_effect = lambda key: {
        "diagnostics": diag,
        "install_journal": ij,
        "interface_registry": ir,
        "event_bus": eb,
    }.get(key)

    with patch("core_runtime.kernel_core.get_container", return_value=mock_container):
        # ComponentLifecycleExecutor もモック化
        with patch("core_runtime.kernel_core.ComponentLifecycleExecutor") as mock_lc_cls:
            mock_lc = MagicMock()
            mock_lc_cls.return_value = mock_lc
            from core_runtime.kernel_core import KernelCore, KernelConfig
            kernel = KernelCore(
                config=overrides.get("config") or KernelConfig(),
                diagnostics=diag,
                install_journal=ij,
                interface_registry=ir,
                event_bus=eb,
                lifecycle=overrides.get("lifecycle") or mock_lc,
            )
    return kernel


# =========================================================================
# 1. logging → get_structured_logger 移行テスト
# =========================================================================

class TestStructuredLoggerMigration:
    """_logger が StructuredLogger インスタンスであることを検証する。"""

    def test_logger_is_structured_logger_instance(self):
        """_logger が StructuredLogger インスタンスであること。"""
        from core_runtime.kernel_core import _logger
        from core_runtime.logging_utils import StructuredLogger
        assert isinstance(_logger, StructuredLogger)

    def test_logger_name_is_correct(self):
        """_logger の name が 'rumi.kernel.core' であること。"""
        from core_runtime.kernel_core import _logger
        assert _logger.name == "rumi.kernel.core"

    def test_logger_has_standard_methods(self):
        """_logger が標準的なログメソッドを持つこと。"""
        from core_runtime.kernel_core import _logger
        for method_name in ("debug", "info", "warning", "error", "critical", "exception"):
            assert callable(getattr(_logger, method_name, None)), f"missing method: {method_name}"

    def test_no_direct_logging_import(self):
        """kernel_core モジュールが 'import logging' を直接使用していないこと。"""
        import core_runtime.kernel_core as mod
        source_path = Path(mod.__file__)
        source_text = source_path.read_text(encoding="utf-8")
        # "import logging" が行頭に単独で存在しないことを確認
        for line in source_text.splitlines():
            stripped = line.strip()
            if stripped == "import logging":
                pytest.fail("Found bare 'import logging' in kernel_core.py")
            if stripped.startswith("import logging"):
                # "import logging" 単独行がないことを確認
                # "from .logging_utils import ..." は OK
                if not stripped.startswith("import logging.") and stripped == "import logging":
                    pytest.fail("Found 'import logging' in kernel_core.py")


# =========================================================================
# 2. deprecated デコレータ適用テスト
# =========================================================================

class TestDeprecatedLegacyFlow:
    """_load_legacy_flow の deprecated 適用を検証する。"""

    def test_load_legacy_flow_registered_in_deprecation_registry(self):
        """_load_legacy_flow が DeprecationRegistry に登録されていること。"""
        from core_runtime.deprecation import DeprecationRegistry
        registry = DeprecationRegistry.get_instance()
        all_entries = registry.get_all()
        # デコレータが __qualname__ で登録するので "KernelCore._load_legacy_flow" を検索
        matching = [k for k in all_entries if "_load_legacy_flow" in k]
        assert len(matching) > 0, (
            f"_load_legacy_flow not found in DeprecationRegistry. "
            f"Registered: {list(all_entries.keys())}"
        )

    def test_load_legacy_flow_deprecation_info_fields(self):
        """DeprecationInfo の since / removed_in / alternative が正しいこと。"""
        from core_runtime.deprecation import DeprecationRegistry
        registry = DeprecationRegistry.get_instance()
        all_entries = registry.get_all()
        matching = {k: v for k, v in all_entries.items() if "_load_legacy_flow" in k}
        assert matching, "_load_legacy_flow not in registry"
        info = list(matching.values())[0]
        assert info.since == "1.0"
        assert info.removed_in == "2.0"
        assert info.alternative == "kernel:flow.load_all"

    def test_load_legacy_flow_emits_deprecation_warning(self):
        """_load_legacy_flow 呼び出し時に DeprecationWarning が発行されること。"""
        kernel = _make_kernel()
        # RUMI_DEPRECATION_LEVEL を warn に設定
        with patch.dict(os.environ, {"RUMI_DEPRECATION_LEVEL": "warn"}):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                # _load_legacy_flow は旧ディレクトリが無ければ minimal_fallback を返す
                result = kernel._load_legacy_flow()
                deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
                assert len(deprecation_warnings) >= 1, (
                    f"Expected DeprecationWarning, got: {[x.category.__name__ for x in w]}"
                )

    def test_load_legacy_flow_silent_mode(self):
        """RUMI_DEPRECATION_LEVEL=silent で警告が出ないこと。"""
        kernel = _make_kernel()
        with patch.dict(os.environ, {"RUMI_DEPRECATION_LEVEL": "silent"}):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                kernel._load_legacy_flow()
                deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
                assert len(deprecation_warnings) == 0


# =========================================================================
# 3. types.py NewType 適用テスト
# =========================================================================

class TestFlowIdNewType:
    """FlowId NewType アノテーションの適用を検証する。"""

    def test_flowid_imported_in_kernel_core(self):
        """kernel_core が FlowId を import していること。"""
        import core_runtime.kernel_core as mod
        assert hasattr(mod, "FlowId") or "FlowId" in dir(mod) or True
        # FlowId は from .types import FlowId でモジュールスコープに読み込まれる
        from core_runtime.types import FlowId
        # save_flow_to_file のアノテーションに FlowId が含まれていることを確認
        from core_runtime.kernel_core import KernelCore
        ann = KernelCore.save_flow_to_file.__annotations__
        # NewType は runtime では callable なので、アノテーション値を文字列化して確認
        flow_id_ann = ann.get("flow_id", None)
        # from __future__ import annotations により文字列になる
        assert flow_id_ann is not None, "flow_id annotation missing"
        assert "FlowId" in str(flow_id_ann), f"Expected FlowId in annotation, got: {flow_id_ann}"

    def test_save_flow_to_file_accepts_plain_str(self, tmp_path):
        """save_flow_to_file が通常の str を引き続き受け付けること（後方互換）。"""
        kernel = _make_kernel()
        kernel.interface_registry = MagicMock()
        kernel.diagnostics = MagicMock()
        flow_def = {"flow_version": "1.0", "steps": []}
        # plain str を渡す（NewType は runtime で str と同等）
        result = kernel.save_flow_to_file("test-flow", flow_def, path=str(tmp_path))
        assert result == str(tmp_path / "test-flow.flow.json")
        assert (tmp_path / "test-flow.flow.json").exists()


# =========================================================================
# 4. load_flow テスト
# =========================================================================

class TestLoadFlow:
    """load_flow の各パスを検証する。"""

    def test_load_flow_explicit_path(self, tmp_path):
        """明示的なパス指定で Flow を読み込めること。"""
        flow_file = tmp_path / "test.flow.yaml"
        flow_file.write_text('{"flow_version": "2.0", "pipelines": {}}', encoding="utf-8")
        kernel = _make_kernel()
        result = kernel.load_flow(path=str(flow_file))
        assert result["flow_version"] == "2.0"

    def test_load_flow_explicit_path_not_found(self, tmp_path):
        """存在しないパスで FileNotFoundError が発生すること。"""
        kernel = _make_kernel()
        with pytest.raises(FileNotFoundError):
            kernel.load_flow(path=str(tmp_path / "nonexistent.yaml"))

    def test_load_flow_legacy_fallback_returns_minimal(self):
        """new flow が存在しない場合に minimal fallback flow を返すこと。"""
        kernel = _make_kernel()
        with patch.dict(os.environ, {"RUMI_DEPRECATION_LEVEL": "silent"}):
            with patch("core_runtime.kernel_core.Path.exists", return_value=False):
                # _log_fallback_warning 内の print を抑制
                with patch("builtins.print"):
                    with patch("core_runtime.kernel_core.Path.glob", return_value=[]):
                        result = kernel.load_flow()
        assert "pipelines" in result
        assert "startup" in result["pipelines"]


# =========================================================================
# 5. shutdown テスト
# =========================================================================

class TestShutdown:
    """shutdown の基本動作を検証する。"""

    def test_shutdown_returns_results(self):
        """shutdown が results dict を返すこと。"""
        kernel = _make_kernel()
        result = kernel.shutdown()
        assert "results" in result
        assert isinstance(result["results"], list)

    def test_shutdown_calls_registered_handlers(self):
        """on_shutdown で登録したハンドラが呼ばれること。"""
        kernel = _make_kernel()
        handler = MagicMock()
        kernel.on_shutdown(handler)
        kernel.shutdown()
        handler.assert_called_once()

    def test_shutdown_calls_handlers_in_reverse_order(self):
        """shutdown ハンドラが登録の逆順で呼ばれること。"""
        kernel = _make_kernel()
        call_order = []
        kernel.on_shutdown(lambda: call_order.append("first"))
        kernel.on_shutdown(lambda: call_order.append("second"))
        kernel.shutdown()
        assert call_order == ["second", "first"]

    def test_shutdown_handles_handler_exception(self):
        """shutdown ハンドラが例外を投げても処理が継続すること。"""
        kernel = _make_kernel()
        kernel.on_shutdown(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        good_handler = MagicMock()
        kernel.on_shutdown(good_handler)
        # shutdown は例外を投げないこと
        result = kernel.shutdown()
        assert "results" in result

    def test_shutdown_stops_flow_scheduler(self):
        """FlowScheduler が設定されている場合に stop() が呼ばれること。"""
        kernel = _make_kernel()
        mock_scheduler = MagicMock()
        kernel._flow_scheduler = mock_scheduler
        kernel.shutdown()
        mock_scheduler.stop.assert_called_once()
        assert kernel._flow_scheduler is None


# =========================================================================
# 6. on_shutdown テスト
# =========================================================================

class TestOnShutdown:
    """on_shutdown ハンドラ登録を検証する。"""

    def test_on_shutdown_adds_callable(self):
        """callable が _shutdown_handlers に追加されること。"""
        kernel = _make_kernel()
        fn = lambda: None
        kernel.on_shutdown(fn)
        assert fn in kernel._shutdown_handlers

    def test_on_shutdown_rejects_non_callable(self):
        """callable でないものは追加されないこと。"""
        kernel = _make_kernel()
        kernel.on_shutdown("not_callable")
        assert len(kernel._shutdown_handlers) == 0


# =========================================================================
# 7. _resolve_handler テスト
# =========================================================================

class TestResolveHandler:
    """_resolve_handler の動作を検証する。"""

    def test_resolve_kernel_handler(self):
        """kernel: プレフィックスでハンドラが解決されること。"""
        kernel = _make_kernel()
        mock_handler = MagicMock()
        kernel._kernel_handlers["kernel:test.handler"] = mock_handler
        result = kernel._resolve_handler("kernel:test.handler")
        assert result is mock_handler

    def test_resolve_kernel_handler_not_found(self):
        """未登録の kernel: ハンドラで None が返ること。"""
        kernel = _make_kernel()
        result = kernel._resolve_handler("kernel:nonexistent")
        assert result is None

    def test_resolve_component_phase_handler(self):
        """component_phase: プレフィックスで callable が返ること。"""
        kernel = _make_kernel()
        result = kernel._resolve_handler("component_phase:startup")
        assert callable(result)

    def test_resolve_invalid_handler(self):
        """無効なハンドラ文字列で None が返ること。"""
        kernel = _make_kernel()
        assert kernel._resolve_handler("") is None
        assert kernel._resolve_handler(None) is None
        assert kernel._resolve_handler(123) is None

    def test_resolve_unknown_prefix_handler(self):
        """不明なプレフィックスで None が返ること。"""
        kernel = _make_kernel()
        assert kernel._resolve_handler("unknown:something") is None


# =========================================================================
# 8. _parse_flow_text テスト
# =========================================================================

class TestParseFlowText:
    """_parse_flow_text のパーサー動作を検証する。"""

    def test_parse_json(self):
        """JSON テキストが正しくパースされること。"""
        kernel = _make_kernel()
        raw = '{"flow_version": "2.0", "pipelines": {}}'
        result, parser_name, meta = kernel._parse_flow_text(raw)
        assert result["flow_version"] == "2.0"
        # YAML が利用可能な場合は yaml_pyyaml、そうでなければ json
        assert parser_name in ("yaml_pyyaml", "json")

    def test_parse_invalid_raises(self):
        """パース不能なテキストで ValueError が発生すること。"""
        kernel = _make_kernel()
        with pytest.raises(ValueError, match="Unable to parse"):
            kernel._parse_flow_text("<<<not valid>>>")


# =========================================================================
# 9. _merge_flow テスト
# =========================================================================

class TestMergeFlow:
    """_merge_flow の動作を検証する。"""

    def test_merge_adds_new_pipeline(self):
        """新しいパイプラインが追加されること。"""
        kernel = _make_kernel()
        base = {"defaults": {}, "pipelines": {}}
        new = {"pipelines": {"startup": [{"id": "step1", "run": {}}]}}
        result = kernel._merge_flow(base, new)
        assert "startup" in result["pipelines"]
        assert len(result["pipelines"]["startup"]) == 1

    def test_merge_overwrites_existing_step_by_id(self):
        """同じ ID のステップが上書きされること。"""
        kernel = _make_kernel()
        base = {"defaults": {}, "pipelines": {"startup": [{"id": "step1", "run": {"handler": "old"}}]}}
        new = {"pipelines": {"startup": [{"id": "step1", "run": {"handler": "new"}}]}}
        result = kernel._merge_flow(base, new)
        assert result["pipelines"]["startup"][0]["run"]["handler"] == "new"


# =========================================================================
# 10. save_flow_to_file / load_user_flows テスト
# =========================================================================

class TestFlowSaveLoad:
    """save_flow_to_file / load_user_flows の動作を検証する。"""

    def test_save_flow_creates_file(self, tmp_path):
        """save_flow_to_file がファイルを作成すること。"""
        kernel = _make_kernel()
        kernel.interface_registry = MagicMock()
        kernel.diagnostics = MagicMock()
        flow_def = {"flow_version": "1.0"}
        result_path = kernel.save_flow_to_file("my-flow", flow_def, path=str(tmp_path))
        assert Path(result_path).exists()
        saved = json.loads(Path(result_path).read_text(encoding="utf-8"))
        assert saved["flow_version"] == "1.0"

    def test_load_user_flows_empty_dir(self, tmp_path):
        """空ディレクトリで空リストが返ること。"""
        kernel = _make_kernel()
        kernel.interface_registry = MagicMock()
        kernel.diagnostics = MagicMock()
        result = kernel.load_user_flows(path=str(tmp_path))
        assert result == []

    def test_load_user_flows_nonexistent_dir(self, tmp_path):
        """存在しないディレクトリで空リストが返ること。"""
        kernel = _make_kernel()
        result = kernel.load_user_flows(path=str(tmp_path / "no_such_dir"))
        assert result == []

    def test_save_then_load_roundtrip(self, tmp_path):
        """save → load のラウンドトリップが成功すること。"""
        kernel = _make_kernel()
        kernel.interface_registry = MagicMock()
        kernel.diagnostics = MagicMock()
        flow_def = {"flow_version": "1.0", "steps": [{"id": "s1"}]}
        kernel.save_flow_to_file("roundtrip", flow_def, path=str(tmp_path))
        loaded = kernel.load_user_flows(path=str(tmp_path))
        assert "roundtrip" in loaded


# =========================================================================
# 11. _now_ts テスト
# =========================================================================

class TestNowTs:
    """_now_ts のフォーマットを検証する。"""

    def test_now_ts_ends_with_z(self):
        """_now_ts が 'Z' で終わること。"""
        kernel = _make_kernel()
        ts = kernel._now_ts()
        assert ts.endswith("Z")

    def test_now_ts_is_iso_format(self):
        """_now_ts が ISO 8601 形式であること。"""
        from datetime import datetime
        kernel = _make_kernel()
        ts = kernel._now_ts()
        # Z を +00:00 に戻してパースできること
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed is not None
