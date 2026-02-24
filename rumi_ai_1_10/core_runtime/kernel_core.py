"""
kernel_core.py - Kernel エンジン本体 (Mixin分割版)

Flowの読み込み、コンテキスト構築、変数解決、shutdown等の
コアロジックを提供する。

Mixin方式でKernelクラスの基底として使用される。
_h_* ハンドラメソッドは含まない（handlers_system / handlers_runtime に分離）。

Flow実行ロジック（run_startup, run_pipeline, execute_flow, _execute_steps_async 等）は
kernel_flow_execution.py の KernelFlowExecutionMixin に分離済み。
"""

from __future__ import annotations

import copy
import json
import os
import importlib.util
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor

from .types import FlowId
from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor
from .capability_proxy import get_capability_proxy
from .paths import BASE_DIR, OFFICIAL_FLOWS_DIR, ECOSYSTEM_DIR, GRANTS_DIR
from .kernel_variable_resolver import VariableResolver, MAX_RESOLVE_DEPTH as _RESOLVER_MAX_DEPTH
from .kernel_context_builder import KernelContextBuilder
from .kernel_flow_converter import FlowConverter
from .kernel_flow_execution import MAX_FLOW_CHAIN_DEPTH  # re-export for backward compat

from .deprecation import deprecated
from .logging_utils import get_structured_logger
_logger = get_structured_logger("rumi.kernel.core")

@dataclass
class KernelConfig:
    flow_path: str = "flow/project.flow.yaml"


MAX_RESOLVE_DEPTH = _RESOLVER_MAX_DEPTH  # re-export from resolver


class KernelCore:
    """
    Kernelエンジン本体

    Flow読み込み・コンテキスト構築・shutdown等のコアロジック。
    Flow実行は KernelFlowExecutionMixin に分離済み。
    _h_* ハンドラは含まない。Mixin基底として使用される。
    """

    def __init__(self, config: Optional[KernelConfig] = None, diagnostics: Optional[Diagnostics] = None,
                 install_journal: Optional[InstallJournal] = None, interface_registry: Optional[InterfaceRegistry] = None,
                 event_bus: Optional[EventBus] = None, lifecycle: Optional[ComponentLifecycleExecutor] = None) -> None:
        from .di_container import get_container
        _c = get_container()

        self.config = config or KernelConfig()
        self.diagnostics = diagnostics or _c.get("diagnostics")
        self.install_journal = install_journal or _c.get("install_journal")
        self.interface_registry = interface_registry or _c.get("interface_registry")
        self.event_bus = event_bus or _c.get("event_bus")
        self.lifecycle = lifecycle or ComponentLifecycleExecutor(diagnostics=self.diagnostics, install_journal=self.install_journal)
        self._flow: Optional[Dict[str, Any]] = None
        self._kernel_handlers: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}
        self._shutdown_handlers: List[Callable[[], None]] = []
        self._capability_proxy = None
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
        self._flow_scheduler = None  # FlowScheduler instance (lazy)
        self._uds_proxy_manager = None  # UDS Egress Proxy Manager


        # K-1: 委譲オブジェクト
        self._variable_resolver = VariableResolver(max_depth=MAX_RESOLVE_DEPTH)
        self._context_builder = KernelContextBuilder(
            diagnostics=self.diagnostics,
            install_journal=self.install_journal,
            interface_registry=self.interface_registry,
            event_bus=self.event_bus,
            lifecycle=self.lifecycle,
        )
        self._flow_converter = FlowConverter()

        self.install_journal.set_interface_registry(self.interface_registry)

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ------------------------------------------------------------------
    # UDS / Capability Proxy 遅延初期化
    # ------------------------------------------------------------------

    def _get_uds_proxy_manager(self):
        """UDSEgressProxyManagerを取得（遅延初期化）"""
        if self._uds_proxy_manager is None:
            try:
                from .egress_proxy import initialize_uds_egress_proxy
                from .network_grant_manager import get_network_grant_manager
                from .audit_logger import get_audit_logger

                ngm = get_network_grant_manager()
                audit = get_audit_logger()

                self._uds_proxy_manager = initialize_uds_egress_proxy(
                    network_grant_manager=ngm,
                    audit_logger=audit
                )
            except Exception as e:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="uds_proxy.init.auto",
                    handler="kernel:uds_proxy.init",
                    status="failed",
                    error=e
                )
        return self._uds_proxy_manager

    def _get_capability_proxy(self):
        """HostCapabilityProxyServerを取得（遅延初期化）"""
        if self._capability_proxy is None:
            try:
                self._capability_proxy = get_capability_proxy()
                self._capability_proxy.initialize()

                # flow.run 用に Kernel 参照を executor に注入
                from .capability_executor import get_capability_executor
                get_capability_executor().set_kernel(self)
            except Exception as e:
                self.diagnostics.record_step(
                    phase="startup", step_id="capability_proxy.init.auto",
                    handler="kernel:capability_proxy.init", status="failed", error=e,
                )
        return self._capability_proxy

    # ------------------------------------------------------------------
    # Handler 解決
    # ------------------------------------------------------------------

    def _resolve_handler(self, handler: str, args: Dict[str, Any] = None) -> Optional[Callable[[Dict[str, Any], Dict[str, Any]], Any]]:
        if not isinstance(handler, str) or not handler:
            return None
        if handler.startswith("kernel:"):
            return self._kernel_handlers.get(handler)
        if handler.startswith("component_phase:"):
            phase_name = handler.split(":", 1)[1].strip()
            captured_args = dict(args or {})
            def _call(call_args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
                return self.lifecycle.run_phase(phase_name, **{**captured_args, **call_args})
            return _call
        return None

    # ------------------------------------------------------------------
    # Flow 読み込み
    # ------------------------------------------------------------------

    def load_flow(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Flowを読み込む

        優先順位:
        1. flows/00_startup.flow.yaml (new flow - 正)
        2. 旧 flow/ ディレクトリ (fallback only - deprecated)
        """
        # 明示的なパス指定がある場合はそれを使用
        if path:
            return self._load_single_flow(Path(path))

        # 1. New flow (正): flows/00_startup.flow.yaml を試行
        new_flow_path = Path(OFFICIAL_FLOWS_DIR) / "00_startup.flow.yaml"
        if new_flow_path.exists():
            try:
                flow_def = self._load_single_flow(new_flow_path)

                # new flow形式をpipelines形式に変換
                if "steps" in flow_def and "pipelines" not in flow_def:
                    flow_def = self._convert_new_flow_to_pipelines(flow_def)

                self._flow = flow_def
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="flow.load.new_flow",
                    handler="kernel:flow.load",
                    status="success",
                    meta={"file": str(new_flow_path), "mode": "new_flow"}
                )
                return self._flow
            except Exception as e:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="flow.load.new_flow.failed",
                    handler="kernel:flow.load",
                    status="failed",
                    error=e,
                    meta={"file": str(new_flow_path)}
                )
                # new flow の読み込みに失敗した場合、fallback へ

        # 2. Fallback (deprecated): 旧 flow/ ディレクトリ
        self._log_fallback_warning()
        return self._load_legacy_flow()

    def _log_fallback_warning(self) -> None:
        """旧flow使用時の警告をログに記録"""
        warning_msg = (
            "Using legacy flow path (flow/). This is DEPRECATED. "
            "The canonical flow system is FlowLoader + FlowModifier via flows/00_startup.flow.yaml. "
            "Legacy flow/ is fallback only and will be removed in a future version. "
            "Startup must use kernel:flow.load_all to load the new flow system."
        )
        print(f"[Rumi] WARNING: {warning_msg}")
        import sys as _sys
        print(f"[Rumi] WARNING: {warning_msg}", file=_sys.stderr)

        self.diagnostics.record_step(
            phase="startup",
            step_id="flow.load.fallback_warning",
            handler="kernel:flow.load",
            status="success",
            meta={"warning": warning_msg, "mode": "legacy_fallback"}
        )

        # 監査ログにも記録
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="legacy_flow_fallback",
                success=True,
                details={"warning": warning_msg, "deprecated": True}
            )
        except Exception:
            pass

    @deprecated(since="1.0", removed_in="2.0", alternative="kernel:flow.load_all")
    def _load_legacy_flow(self) -> Dict[str, Any]:
        """旧形式のflowを読み込む（fallback用）"""
        merged = {
            "flow_version": "2.0",
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {}
        }

        # 旧ディレクトリを読み込み（互換性のため）
        for legacy_dir in [str(BASE_DIR / "flow" / "core"), str(BASE_DIR / "flow" / "ecosystem"), str(BASE_DIR / "flow")]:
            legacy_path = Path(legacy_dir)
            if legacy_path.exists():
                yaml_files = sorted(legacy_path.glob("*.flow.yaml"))
                for yaml_file in yaml_files:
                    try:
                        single = self._load_single_flow(yaml_file)
                        merged = self._merge_flow(merged, single, yaml_file)
                        self.diagnostics.record_step(
                            phase="startup",
                            step_id=f"flow.load.legacy.{yaml_file.name}",
                            handler="kernel:flow.load",
                            status="success",
                            meta={"file": str(yaml_file), "source": "legacy", "deprecated": True}
                        )
                    except Exception as e:
                        self.diagnostics.record_step(
                            phase="startup",
                            step_id=f"flow.load.legacy.{yaml_file.name}",
                            handler="kernel:flow.load",
                            status="failed",
                            error=e,
                            meta={"file": str(yaml_file), "source": "legacy"}
                        )

        if not merged["pipelines"]:
            self._flow = self._minimal_fallback_flow()
            return self._flow

        self._flow = merged
        return self._flow

    def _convert_new_flow_to_pipelines(self, flow_def: Dict[str, Any]) -> Dict[str, Any]:
        """後方互換ラッパー。FlowConverter に委譲 (M-10)。"""
        return self._flow_converter.convert_new_flow_to_pipelines(flow_def)


    def _merge_flow(self, base: Dict[str, Any], new: Dict[str, Any], source_file: Path = None) -> Dict[str, Any]:
        result = copy.deepcopy(base)

        if "defaults" in new:
            result["defaults"].update(new["defaults"])

        for pipeline_name, steps in new.get("pipelines", {}).items():
            if not isinstance(steps, list):
                continue

            if pipeline_name not in result["pipelines"]:
                result["pipelines"][pipeline_name] = []

            existing_ids = {s.get("id") for s in result["pipelines"][pipeline_name] if s.get("id")}

            for step in steps:
                step_id = step.get("id")
                if step_id and step_id in existing_ids:
                    result["pipelines"][pipeline_name] = [
                        step if s.get("id") == step_id else s
                        for s in result["pipelines"][pipeline_name]
                    ]
                else:
                    result["pipelines"][pipeline_name].append(step)

        return result

    def _load_single_flow(self, flow_path: Path) -> Dict[str, Any]:
        if not flow_path.exists():
            raise FileNotFoundError(f"Flow file not found: {flow_path}")
        raw = flow_path.read_text(encoding="utf-8")
        parsed, _, _ = self._parse_flow_text(raw)
        return parsed

    def _minimal_fallback_flow(self) -> Dict[str, Any]:
        return {
            "flow_version": "2.0",
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {
                "startup": [
                    {"id": "fallback.mounts", "run": {"handler": "kernel:mounts.init", "args": {"mounts_file": str(BASE_DIR / "user_data" / "mounts.json")}}},
                    {"id": "fallback.registry", "run": {"handler": "kernel:registry.load", "args": {"ecosystem_dir": ECOSYSTEM_DIR}}},
                    {"id": "fallback.active", "run": {"handler": "kernel:active_ecosystem.load", "args": {"config_file": str(BASE_DIR / "user_data" / "active_ecosystem.json")}}}
                ]
            }
        }

    def _parse_flow_text(self, raw: str) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        attempts: List[Dict[str, Any]] = []
        try:
            import yaml
            try:
                parsed_any = yaml.safe_load(raw)
                if isinstance(parsed_any, dict):
                    return parsed_any, "yaml_pyyaml", {"parser_attempts": attempts}
                attempts.append({"name": "yaml_pyyaml", "status": "failed", "reason": f"returned {type(parsed_any).__name__}"})
            except Exception as e:
                attempts.append({"name": "yaml_pyyaml", "status": "failed", "reason": str(e)})
        except Exception as e:
            attempts.append({"name": "yaml_pyyaml", "status": "unavailable", "reason": str(e)})
        try:
            parsed_any = json.loads(raw)
            if isinstance(parsed_any, dict):
                return parsed_any, "json", {"parser_attempts": attempts}
            attempts.append({"name": "json", "status": "failed", "reason": f"returned {type(parsed_any).__name__}"})
        except Exception as e:
            attempts.append({"name": "json", "status": "failed", "reason": str(e)})
        raise ValueError("Unable to parse Flow as YAML or JSON")

    # ------------------------------------------------------------------
    # Flow 保存 / ユーザーFlow読み込み
    # ------------------------------------------------------------------

    def save_flow_to_file(self, flow_id: FlowId, flow_def: Dict[str, Any], path: str = None) -> str:
        if path is None:
            path = str(BASE_DIR / "user_data" / "flows")
        flow_dir = Path(path)
        flow_dir.mkdir(parents=True, exist_ok=True)
        file_path = flow_dir / f"{flow_id}.flow.json"
        file_path.write_text(json.dumps(flow_def, ensure_ascii=False, indent=2), encoding="utf-8")
        self.interface_registry.register(f"flow.{flow_id}", flow_def)
        self.diagnostics.record_step(phase="flow", step_id=f"flow.{flow_id}.save", handler="kernel:save_flow",
                                      status="success", meta={"path": str(file_path)})
        return str(file_path)

    def load_user_flows(self, path: str = None) -> List[str]:
        if path is None:
            path = str(BASE_DIR / "user_data" / "flows")
        flow_dir = Path(path)
        if not flow_dir.exists():
            return []
        loaded: List[str] = []
        for f in flow_dir.glob("*.flow.json"):
            try:
                flow_def = json.loads(f.read_text(encoding="utf-8"))
                self.interface_registry.register(f"flow.{f.stem}", flow_def)
                loaded.append(f.stem)
                self.diagnostics.record_step(phase="startup", step_id=f"flow.{f.stem}.load", handler="kernel:load_user_flows",
                                              status="success", meta={"path": str(f)})
            except Exception as e:
                self.diagnostics.record_step(phase="startup", step_id=f"flow.{f.stem}.load", handler="kernel:load_user_flows",
                                              status="failed", error=e, meta={"path": str(f)})
        return loaded

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def on_shutdown(self, fn: Callable[[], None]) -> None:
        if callable(fn):
            self._shutdown_handlers.append(fn)

    # ------------------------------------------------------------------
    # Flow Scheduler
    # ------------------------------------------------------------------

    def start_flow_scheduler(self) -> Dict[str, Any]:
        """
        FlowScheduler を初期化・起動する。

        InterfaceRegistry に登録されている全 Flow から schedule フィールドを
        スキャンし、スケジュールテーブルを構築して起動する。
        Kernel を直接参照せず、execute_flow_sync コールバックで疎結合。

        Returns:
            {"started": bool, "registered_count": int, "entries": [...]}
        """
        try:
            from .flow_scheduler import FlowScheduler, scan_flows_for_schedules
        except ImportError as e:
            self.diagnostics.record_step(
                phase="scheduler", step_id="scheduler.import.failed",
                handler="kernel:flow_scheduler.start", status="failed", error=e,
            )
            return {"started": False, "registered_count": 0, "error": str(e)}

        scheduler = FlowScheduler(
            execute_callback=self.execute_flow_sync,
            diagnostics_callback=self.diagnostics.record_step,
        )

        scheduled_flows = scan_flows_for_schedules(self.interface_registry)
        registered = 0
        for item in scheduled_flows:
            if scheduler.register(item["flow_id"], item["schedule"]):
                registered += 1

        if registered > 0:
            scheduler.start()
            self._flow_scheduler = scheduler

        self.diagnostics.record_step(
            phase="scheduler", step_id="scheduler.start",
            handler="kernel:flow_scheduler.start", status="success",
            meta={"registered_count": registered, "started": registered > 0},
        )

        return {
            "started": registered > 0,
            "registered_count": registered,
            "entries": [f["flow_id"] for f in scheduled_flows],
        }

    def shutdown(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []

        # FlowScheduler を停止
        if self._flow_scheduler is not None:
            try:
                self._flow_scheduler.stop()
                results.append({"handler": "flow_scheduler", "status": "success"})
            except Exception as e:
                results.append({"handler": "flow_scheduler", "status": "failed", "error": str(e)})
            self._flow_scheduler = None

        # Capability proxy を停止
        if self._capability_proxy:
            try:
                self._capability_proxy.stop_all()
                results.append({"handler": "capability_proxy", "status": "success"})
            except Exception as e:
                results.append({"handler": "capability_proxy", "status": "failed", "error": str(e)})

        # UDSプロキシを停止
        if self._uds_proxy_manager:
            try:
                self._uds_proxy_manager.stop_all()
                results.append({"handler": "uds_proxy_manager", "status": "success"})
            except Exception as e:
                results.append({"handler": "uds_proxy_manager", "status": "failed", "error": str(e)})

        for fn in reversed(self._shutdown_handlers):
            try:
                fn()
                results.append({"handler": getattr(fn, "__name__", str(fn)), "status": "success"})
            except Exception as e:
                results.append({"handler": getattr(fn, "__name__", str(fn)), "status": "failed", "error": str(e)})
        try:
            self.event_bus.clear()
        except Exception:
            pass
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
        self.diagnostics.record_step(phase="shutdown", step_id="kernel.shutdown", handler="kernel:shutdown",
                                      status="success", meta={"handlers_count": len(results)})
        return {"results": results}

    # ------------------------------------------------------------------
    # Kernel Context 構築
    # ------------------------------------------------------------------

    def _build_kernel_context(self) -> Dict[str, Any]:
        """KernelContextBuilder に委譲。M-7: Null安全対応済み。"""
        return self._context_builder.build()

    # ------------------------------------------------------------------
    # 変数解決
    # ------------------------------------------------------------------

    def _resolve_value(self, value, ctx, depth=0):
        """後方互換ラッパー。VariableResolver に委譲 (K-1)。"""
        return self._variable_resolver.resolve_value(value, ctx, depth)

    def _resolve_args(self, args, ctx):
        """後方互換ラッパー。VariableResolver に委譲 (K-1)。"""
        return self._variable_resolver.resolve_args(args, ctx)
