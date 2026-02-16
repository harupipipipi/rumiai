"""
kernel_core.py - Kernel エンジン本体 (Mixin分割)

Flowの読み込み・実行、コンテキスト構築、変数解決、shutdown等の
コアロジックを提供する。

Mixin方式でKernelクラスの基底として使用される。
_h_* ハンドラメソッドは含まない（handlers_system / handlers_runtime に分離）。
"""

from __future__ import annotations

import copy
import json
import asyncio
import os
import uuid
import importlib.util
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor

from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor
from .capability_proxy import get_capability_proxy
from .paths import BASE_DIR, OFFICIAL_FLOWS_DIR, ECOSYSTEM_DIR, GRANTS_DIR
import re

@dataclass
class KernelConfig:
    flow_path: str = "flow/project.flow.yaml"


# --- Flow chain / resolve depth limits (Fix #58, #70) ---
MAX_FLOW_CHAIN_DEPTH = 10
MAX_RESOLVE_DEPTH = 20

# --- Condition parser pattern (Fix #16) ---
_CONDITION_OP_RE = re.compile(r'\s+(==|!=)\s+')


class KernelCore:
    """
    Kernelエンジン本体

    Flow読み込み・実行・コンテキスト構築・shutdown等のコアロジック。
    _h_* ハンドラは含まない。Mixin基底として使用される。
    """

    def __init__(self, config: Optional[KernelConfig] = None, diagnostics: Optional[Diagnostics] = None,
                 install_journal: Optional[InstallJournal] = None, interface_registry: Optional[InterfaceRegistry] = None,
                 event_bus: Optional[EventBus] = None, lifecycle: Optional[ComponentLifecycleExecutor] = None) -> None:
        self.config = config or KernelConfig()
        self.diagnostics = diagnostics or Diagnostics()
        self.install_journal = install_journal or InstallJournal()
        self.interface_registry = interface_registry or InterfaceRegistry()
        self.event_bus = event_bus or EventBus()
        self.lifecycle = lifecycle or ComponentLifecycleExecutor(diagnostics=self.diagnostics, install_journal=self.install_journal)
        self._flow: Optional[Dict[str, Any]] = None
        self._kernel_handlers: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}
        self._shutdown_handlers: List[Callable[[], None]] = []
        self._capability_proxy = None
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
        self._flow_scheduler = None  # FlowScheduler instance (lazy)
        self._uds_proxy_manager = None  # UDS Egress Proxy Manager

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
        """
        New flow形式（phases/steps）をpipelines形式に変換

        Kernel.run_startup() が pipelines 形式を期待しているため
        """
        result = {
            "flow_version": "2.0",
            "defaults": flow_def.get("defaults", {"fail_soft": True, "on_missing_handler": "skip"}),
            "pipelines": {"startup": []}
        }
        # C4: preserve schedule field through conversion
        if flow_def.get("schedule"):
            result["schedule"] = flow_def["schedule"]

        steps = flow_def.get("steps", [])
        phases = flow_def.get("phases", [])

        # phase順 → priority順 → id順 でソート
        phase_order = {p: i for i, p in enumerate(phases)}
        sorted_steps = sorted(
            steps,
            key=lambda s: (phase_order.get(s.get("phase", ""), 999), s.get("priority", 100), s.get("id", ""))
        )

        # pipelines形式に変換
        for step in sorted_steps:
            pipeline_step = {
                "id": step.get("id"),
                "run": {}
            }

            # type による変換
            step_type = step.get("type", "handler")
            step_input = step.get("input", {})

            if step_type == "handler":
                if isinstance(step_input, dict):
                    pipeline_step["run"]["handler"] = step_input.get("handler", "kernel:noop")
                    pipeline_step["run"]["args"] = step_input.get("args", {})
                else:
                    pipeline_step["run"]["handler"] = "kernel:noop"
                    pipeline_step["run"]["args"] = {}
            elif step_type == "python_file_call":
                pipeline_step["run"]["handler"] = "kernel:python_file_call"
                pipeline_step["run"]["args"] = {
                    "file": step.get("file"),
                    "owner_pack": step.get("owner_pack"),
                    "principal_id": step.get("principal_id"),
                    "input": step_input,
                    "timeout_seconds": step.get("timeout_seconds", 60.0),
                    "_step_id": step.get("id"),
                    "_phase": step.get("phase"),
                }
            else:
                pipeline_step["run"]["handler"] = "kernel:noop"
                pipeline_step["run"]["args"] = {}

            # when条件があれば追加
            if step.get("when"):
                pipeline_step["when"] = step["when"]

            # output があれば追加
            if step.get("output"):
                pipeline_step["output"] = step["output"]

            result["pipelines"]["startup"].append(pipeline_step)

        return result

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
    # Startup / Pipeline 実行
    # ------------------------------------------------------------------

    def run_startup(self) -> Dict[str, Any]:
        self.load_user_flows()
        flow = self._flow or self.load_flow()
        defaults = flow.get("defaults", {}) if isinstance(flow, dict) else {}
        fail_soft_default = bool(defaults.get("fail_soft", True))
        on_missing_handler = str(defaults.get("on_missing_handler", "skip")).strip().lower()
        pipelines = flow.get("pipelines", {})
        startup_steps = pipelines.get("startup", []) if isinstance(pipelines, dict) else []
        startup_steps = startup_steps if isinstance(startup_steps, list) else []
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {"fail_soft": fail_soft_default, "on_missing_handler": on_missing_handler}
        self.diagnostics.record_step(phase="startup", step_id="startup.pipeline.start", handler="kernel:startup.run",
                                      status="success", meta={"step_count": len(startup_steps)})
        aborted = False
        for step in startup_steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="startup", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(phase="startup", step_id="startup.pipeline.internal_error",
                                              handler="kernel:startup.run", status="failed", error=e)
                if not fail_soft_default:
                    break
        self.diagnostics.record_step(phase="startup", step_id="startup.pipeline.end", handler="kernel:startup.run",
                                      status="success" if not aborted else "failed", meta={"aborted": aborted})
        return self.diagnostics.as_dict()

    def run_pipeline(self, pipeline_name: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        flow = self._flow or self.load_flow()
        defaults = flow.get("defaults", {}) if isinstance(flow, dict) else {}
        fail_soft_default = bool(defaults.get("fail_soft", True))
        pipelines = flow.get("pipelines", {})
        steps = pipelines.get(pipeline_name, []) if isinstance(pipelines, dict) else []
        steps = steps if isinstance(steps, list) else []

        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {
            "fail_soft": fail_soft_default,
            "on_missing_handler": str(defaults.get("on_missing_handler", "skip")).lower()
        }
        if context:
            ctx.update(context)

        self.diagnostics.record_step(
            phase=pipeline_name,
            step_id=f"{pipeline_name}.pipeline.start",
            handler=f"kernel:{pipeline_name}.run",
            status="success",
            meta={"step_count": len(steps), "pipeline": pipeline_name}
        )

        aborted = False
        for step in steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase=pipeline_name, ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(
                    phase=pipeline_name,
                    step_id=f"{pipeline_name}.pipeline.internal_error",
                    handler=f"kernel:{pipeline_name}.run",
                    status="failed",
                    error=e
                )
                if not fail_soft_default:
                    break

        self.diagnostics.record_step(
            phase=pipeline_name,
            step_id=f"{pipeline_name}.pipeline.end",
            handler=f"kernel:{pipeline_name}.run",
            status="success" if not aborted else "failed",
            meta={"aborted": aborted, "pipeline": pipeline_name}
        )

        return ctx

    # ------------------------------------------------------------------
    # Async Flow 実行
    # ------------------------------------------------------------------

    async def execute_flow(self, flow_id: str, context: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        if timeout:
            try:
                return await asyncio.wait_for(self._execute_flow_internal(flow_id, context), timeout=timeout)
            except asyncio.TimeoutError:
                return {"_error": f"Flow '{flow_id}' timed out after {timeout}s", "_flow_timeout": True}
        return await self._execute_flow_internal(flow_id, context)

    def execute_flow_sync(self, flow_id: str, context: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        effective_timeout = timeout or 300
        try:
            asyncio.get_running_loop()
            from concurrent.futures import TimeoutError as FuturesTimeoutError
            with ThreadPoolExecutor() as pool:
                try:
                    return pool.submit(asyncio.run, self.execute_flow(flow_id, context, timeout)).result(timeout=effective_timeout)
                except FuturesTimeoutError:
                    return {"_error": f"Flow '{flow_id}' timed out after {effective_timeout}s (sync)", "_flow_timeout": True}
        except RuntimeError:
            return asyncio.run(self.execute_flow(flow_id, context, timeout))

    async def _execute_flow_internal(self, flow_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = self._build_kernel_context()
        ctx.update(context or {})
        execution_id = str(uuid.uuid4())
        ctx["_flow_id"] = flow_id
        ctx["_flow_execution_id"] = execution_id
        ctx["_flow_timeout"] = False
        call_stack = ctx.setdefault("_flow_call_stack", [])

        # Fix #58: chain depth limit
        if len(call_stack) >= MAX_FLOW_CHAIN_DEPTH:
            return {
                "_error": f"Flow chain depth limit exceeded ({MAX_FLOW_CHAIN_DEPTH}): {' -> '.join(call_stack)} -> {flow_id}",
                "_flow_call_stack": list(call_stack),
            }

        if flow_id in call_stack:
            return {"_error": f"Recursive flow detected: {' -> '.join(call_stack)} -> {flow_id}", "_flow_call_stack": list(call_stack)}
        call_stack.append(flow_id)
        try:
            flow_def = self.interface_registry.get(f"flow.{flow_id}", strategy="last")
            if flow_def is None:
                available = [k[5:] for k in (self.interface_registry.list() or {}).keys()
                            if k.startswith("flow.") and not k.startswith("flow.hooks") and not k.startswith("flow.construct")]
                return {"_error": f"Flow '{flow_id}' not found", "_available": available}
            steps = flow_def.get("steps", [])
            ctx["_total_steps"] = len(steps)
            self.diagnostics.record_step(phase="flow", step_id=f"flow.{flow_id}.start", handler="kernel:execute_flow",
                                          status="success", meta={"flow_id": flow_id, "execution_id": execution_id, "step_count": len(steps)})
            ctx = await self._execute_steps_async(steps, ctx)
            self.diagnostics.record_step(phase="flow", step_id=f"flow.{flow_id}.end", handler="kernel:execute_flow",
                                          status="success", meta={"flow_id": flow_id, "execution_id": execution_id})
            return ctx
        finally:
            call_stack.pop()

    async def _execute_steps_async(self, steps: List[Dict[str, Any]], ctx: Dict[str, Any]) -> Dict[str, Any]:
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or ctx.get("_flow_timeout"):
                continue
            ctx["_current_step_index"] = i
            step_id = step.get("id", f"step_{i}")
            step_type = step.get("type", "handler")
            if step.get("when") and not self._eval_condition(step["when"], ctx):
                continue
            meta = {"flow_id": ctx.get("_flow_id"), "execution_id": ctx.get("_flow_execution_id"),
                    "step_index": i, "total_steps": ctx.get("_total_steps", len(steps)),
                    "parent_execution_id": ctx.get("_parent_flow_execution_id")}
            should_skip, should_abort = False, False
            for hook in self.interface_registry.get("flow.hooks.before_step", strategy="all"):
                if callable(hook):
                    try:
                        result = hook(step, ctx, meta)
                        if isinstance(result, dict):
                            if result.get("_skip"):
                                should_skip = True
                                break
                            if result.get("_abort"):
                                should_abort = True
                                break
                    except Exception as e:
                        self.diagnostics.record_step(phase="flow", step_id=f"{step_id}.before_hook",
                                                      handler="flow.hooks.before_step", status="failed", error=e)
            if should_abort:
                return ctx
            if should_skip:
                continue
            step_result = None
            try:
                if step_type == "handler":
                    ctx, step_result = await self._execute_handler_step_async(step, ctx)
                elif step_type == "flow":
                    ctx, step_result = await self._execute_sub_flow_step(step, ctx)
                else:
                    construct = self.interface_registry.get(f"flow.construct.{step_type}")
                    if construct and callable(construct):
                        ctx = await construct(self, step, ctx) if asyncio.iscoroutinefunction(construct) else construct(self, step, ctx)
                # C5: check flow control abort after step execution
                if ctx.get("_flow_control_abort"):
                    return ctx
                for hook in self.interface_registry.get("flow.hooks.after_step", strategy="all"):
                    if callable(hook):
                        try:
                            hook(step, ctx, step_result, meta)
                        except Exception:
                            pass
            except Exception as e:
                error_handler = self.interface_registry.get("flow.error_handler")
                if error_handler and callable(error_handler):
                    try:
                        action = error_handler(step, ctx, e)
                        if action == "abort":
                            self.diagnostics.record_step(phase="flow", step_id=f"{step_id}.error",
                                                          handler=step.get("handler", "unknown"), status="failed", error=e, meta={"action": "abort"})
                            return ctx
                        if action == "retry":
                            continue
                    except Exception:
                        pass
                self.diagnostics.record_step(phase="flow", step_id=f"{step_id}.error",
                                              handler=step.get("handler", "unknown"), status="failed", error=e, meta={"action": "continue"})
        return ctx

    async def _execute_handler_step_async(self, step: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        handler_key = step.get("handler")
        if not handler_key:
            return ctx, None
        resolved_args = self._resolve_value(step.get("args", {}), ctx)

        # handler 解決統一: kernel:* は _resolve_handler を優先し、
        # pipeline 実行と同じ経路で解決する（async/pipeline 非対称の解消）
        handler = self._resolve_handler(handler_key, resolved_args)

        # kernel:* で見つからなかった場合は IR にフォールバック
        if handler is None:
            handler = self.interface_registry.get(handler_key, strategy="last")

        if handler is None or not callable(handler):
            return ctx, None
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(resolved_args, ctx)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(self._executor, lambda: handler(resolved_args, ctx))
            # C7: unwrap output — strip _kernel_step_status wrapper
            unwrapped = result["output"] if isinstance(result, dict) and "output" in result else result

            # C5: flow control protocol — check for abort signal
            if isinstance(unwrapped, dict) and unwrapped.get("__flow_control") == "abort":
                output_key = step.get("output")
                if output_key:
                    ctx[output_key] = unwrapped
                ctx["_flow_control_abort"] = True
                ctx["_flow_control_abort_reason"] = unwrapped.get("reason", "abort requested by step")
                self.diagnostics.record_step(
                    phase="flow",
                    step_id=f"{step.get('id', 'unknown')}.flow_control_abort",
                    handler=step.get("handler", "unknown"),
                    status="aborted",
                    meta={"reason": ctx["_flow_control_abort_reason"], "__flow_control": "abort"}
                )
                return ctx, unwrapped

            if step.get("output"):
                # vocab normalization: dict キーを優先語に正規化
                if isinstance(unwrapped, dict) and step.get("vocab_normalize", True):
                    unwrapped = self._vocab_normalize_output(unwrapped, step, ctx)
                ctx[step["output"]] = unwrapped
            return ctx, unwrapped
        except Exception:
            raise

    async def _execute_sub_flow_step(self, step: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        flow_name = step.get("flow")
        if not flow_name:
            return ctx, None

        call_stack = ctx.get("_flow_call_stack", [])

        # Fix #58: chain depth limit
        if len(call_stack) >= MAX_FLOW_CHAIN_DEPTH:
            error_msg = f"Flow chain depth limit exceeded ({MAX_FLOW_CHAIN_DEPTH}): {' -> '.join(call_stack)} -> {flow_name}"
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.depth_limit",
                handler="kernel:subflow",
                status="failed",
                error={"type": "FlowChainDepthError", "message": error_msg}
            )
            return ctx, {"_error": error_msg}

        if flow_name in call_stack:
            error_msg = f"Recursive flow detected: {' -> '.join(call_stack)} -> {flow_name}"
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.recursive",
                handler="kernel:subflow",
                status="failed",
                error={"type": "RecursiveFlowError", "message": error_msg}
            )
            return ctx, {"_error": error_msg}

        child_ctx = copy.deepcopy(ctx)
        child_ctx["_flow_call_stack"] = call_stack + [flow_name]
        child_ctx["_parent_flow_id"] = ctx.get("_flow_id")

        args = step.get("args", {})
        resolved_args = self._resolve_value(args, ctx)
        if isinstance(resolved_args, dict):
            child_ctx.update(resolved_args)

        try:
            flow_def = self.interface_registry.get(f"flow.{flow_name}", strategy="last")

            if flow_def is None:
                ecosystem_flow_path = BASE_DIR / "flow" / "ecosystem" / f"{flow_name}.flow.yaml"
                if ecosystem_flow_path.exists():
                    flow_def = self._load_single_flow(ecosystem_flow_path)
                    if "pipelines" in flow_def:
                        first_pipeline = list(flow_def["pipelines"].values())[0]
                        flow_def = {"steps": first_pipeline}

            if flow_def is None:
                self.diagnostics.record_step(
                    phase="flow",
                    step_id=f"subflow.{flow_name}.not_found",
                    handler="kernel:subflow",
                    status="failed",
                    error={"type": "FlowNotFoundError", "message": f"Flow '{flow_name}' not found"}
                )
                return ctx, {"_error": f"Flow '{flow_name}' not found"}

            steps = flow_def.get("steps", [])
            if not steps and "pipelines" in flow_def:
                first_pipeline = list(flow_def["pipelines"].values())[0]
                steps = first_pipeline if isinstance(first_pipeline, list) else []

            child_ctx["_flow_id"] = flow_name
            child_ctx = await self._execute_steps_async(steps, child_ctx)

            result = child_ctx.get("output") or child_ctx.get("result") or child_ctx

            output_key = step.get("output")
            if output_key:
                ctx[output_key] = result

            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.complete",
                handler="kernel:subflow",
                status="success",
                meta={"flow_name": flow_name, "output_key": output_key}
            )

            return ctx, result

        except Exception as e:
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.error",
                handler="kernel:subflow",
                status="failed",
                error=e,
                meta={"flow_name": flow_name}
            )
            return ctx, {"_error": str(e)}

    # ------------------------------------------------------------------
    # 条件評価
    # ------------------------------------------------------------------

    def _eval_condition(self, condition: str, ctx: Dict[str, Any]) -> bool:
        """条件式を評価する。

        Fix #16: 正規表現で最初の演算子を検出し分割する。
        左辺は変数参照（スペース付き演算子を含まない）前提。
        値側に " == " や " != " が含まれていても誤動作しない。
        """
        condition = condition.strip()

        # 最初の == or != 演算子を検出（左辺は変数参照なので演算子を含まない前提）
        m = _CONDITION_OP_RE.search(condition)
        if m:
            op = m.group(1)  # "==" or "!="
            left = condition[:m.start()].strip()
            right = condition[m.end():].strip()

            left_val = self._resolve_value(left, ctx)
            right_val = right.strip('"\'')

            if right_val.lower() == "true":
                target = True
            elif right_val.lower() == "false":
                target = False
            else:
                try:
                    target = int(right_val)
                except ValueError:
                    target = right_val

            if op == "==":
                if isinstance(target, (bool, int)):
                    return left_val == target
                return str(left_val) == target
            else:  # "!="
                if isinstance(target, (bool, int)):
                    return left_val != target
                return str(left_val) != target

        return bool(self._resolve_value(condition, ctx))

    # ------------------------------------------------------------------
    # Flow 保存 / ユーザーFlow読み込み
    # ------------------------------------------------------------------

    def save_flow_to_file(self, flow_id: str, flow_def: Dict[str, Any], path: str = None) -> str:
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
        ctx: Dict[str, Any] = {"diagnostics": self.diagnostics, "install_journal": self.install_journal,
                               "interface_registry": self.interface_registry, "event_bus": self.event_bus,
                               "lifecycle": self.lifecycle, "mount_manager": None, "registry": None, "active_ecosystem": None}
        try:
            from backend_core.ecosystem.mounts import get_mount_manager
            ctx["mount_manager"] = get_mount_manager()
        except Exception:
            pass
        try:
            from backend_core.ecosystem.registry import get_registry
            ctx["registry"] = get_registry()
        except Exception:
            pass
        try:
            from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager
            ctx["active_ecosystem"] = get_active_ecosystem_manager()
        except Exception:
            pass
        try:
            self.lifecycle.interface_registry = self.interface_registry
            self.lifecycle.event_bus = self.event_bus
        except Exception:
            pass
        ctx.setdefault("_disabled_targets", {"packs": set(), "components": set()})

        try:
            from .permission_manager import get_permission_manager
            ctx["permission_manager"] = get_permission_manager()
        except ImportError:
            pass

        try:
            from .function_alias import get_function_alias_registry
            ctx["function_alias_registry"] = get_function_alias_registry()
        except Exception:
            pass

        try:
            from .flow_composer import get_flow_composer
            ctx["flow_composer"] = get_flow_composer()
        except Exception:
            pass

        try:
            from .di_container import get_container
            ctx["vocab_registry"] = get_container().get_or_none("vocab_registry")
        except Exception:
            pass

        try:
            from .store_registry import get_store_registry
            ctx["store_registry"] = get_store_registry()
        except Exception:
            pass

        try:
            from .unit_registry import get_unit_registry
            ctx["unit_registry"] = get_unit_registry()
        except Exception:
            pass


        return ctx

    # ------------------------------------------------------------------
    # Flow Step 実行（同期・pipeline用）
    # ------------------------------------------------------------------

    def _execute_flow_step(self, step: Any, phase: str, ctx: Dict[str, Any]) -> bool:
        step_id, handler, args, optional, on_error_action = None, None, {}, False, None
        if isinstance(step, dict):
            step_id = step.get("id")
            run = step.get("run", {})
            if isinstance(run, dict):
                handler = run.get("handler")
                run_args = run.get("args", {})
                if isinstance(run_args, dict):
                    args = dict(run_args)
            optional = bool(step.get("optional", False))
            on_error = step.get("on_error", {})
            if isinstance(on_error, dict):
                on_error_action = on_error.get("action")
        step_id_str = str(step_id or "unknown.step")
        handler_str = str(handler or "unknown.handler")
        fn = self._resolve_handler(handler_str, args)
        if fn is None:
            missing_policy = str(ctx.get("_flow_defaults", {}).get("on_missing_handler", "skip")).lower()
            if missing_policy == "error" and not optional:
                self.diagnostics.record_step(phase=phase, step_id=step_id_str, handler=handler_str, status="failed",
                                              error={"type": "MissingHandler", "message": f"handler not found: {handler_str}"},
                                              meta={"optional": optional, "on_missing_handler": missing_policy})
                return True
            self.diagnostics.record_step(phase=phase, step_id=step_id_str, handler=handler_str, status="skipped",
                                          meta={"reason": "missing_handler", "optional": optional, "on_missing_handler": missing_policy})
            return False
        self.diagnostics.record_step(phase=phase, step_id=f"{step_id_str}.start", handler=handler_str, status="success", meta={"args": args})
        try:
            ret = fn(args, ctx)
            done_status = "success"
            done_meta: Dict[str, Any] = {}
            if isinstance(ret, dict):
                maybe_status = ret.get("_kernel_step_status")
                if maybe_status in ("success", "skipped"):
                    done_status = maybe_status
                maybe_meta = ret.get("_kernel_step_meta")
                if isinstance(maybe_meta, dict):
                    done_meta = dict(maybe_meta)
            self.diagnostics.record_step(phase=phase, step_id=f"{step_id_str}.done", handler=handler_str, status=done_status, meta=done_meta)
            return False
        except Exception as e:
            action = str(on_error_action or ("continue" if ctx.get("_flow_defaults", {}).get("fail_soft", True) else "abort")).lower()
            status = "disabled" if action == "disable_target" else "failed"
            self.diagnostics.record_step(phase=phase, step_id=f"{step_id_str}.failed", handler=handler_str, status=status, error=e,
                                          meta={"on_error.action": action, "optional": optional})
            return action == "abort"

    # ------------------------------------------------------------------
    # 変数解決
    # ------------------------------------------------------------------

    def _resolve_value(self, value: Any, ctx: Dict[str, Any], _depth: int = 0) -> Any:
        # Fix #70: recursion depth limit
        if _depth > MAX_RESOLVE_DEPTH:
            return value
        if isinstance(value, dict):
            return {k: self._resolve_value(v, ctx, _depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, ctx, _depth + 1) for item in value]
        if not isinstance(value, str):
            return value
        if not value.startswith("${") or not value.endswith("}"):
            return value
        if value.startswith("${ctx."):
            path = value[6:-1]
            current = ctx
            for part in path.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current
        return ctx.get(value[2:-1])

    def _resolve_args(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self._resolve_value(v, ctx) for k, v in args.items()} if isinstance(args, dict) else {}
