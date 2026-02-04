"""
kernel.py - Flow Runner(用途非依存カーネル)
async対応、Flow Hook、タイムアウト、循環検出対応版
"""

from __future__ import annotations

import copy
import json
import asyncio
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
from .function_alias import FunctionAliasRegistry, get_function_alias_registry
from .flow_composer import FlowComposer, get_flow_composer
from .flow_loader import get_flow_loader, FlowDefinition, FlowStep
from .flow_modifier import get_modifier_loader, get_modifier_applier
from .audit_logger import get_audit_logger
from .python_file_executor import get_python_file_executor, ExecutionContext
from .network_grant_manager import get_network_grant_manager
from .egress_proxy import get_egress_proxy, initialize_egress_proxy, shutdown_egress_proxy
from .lib_executor import get_lib_executor


@dataclass
class KernelConfig:
    flow_path: str = "flow/project.flow.yaml"


class Kernel:
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
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
        
        self.install_journal.set_interface_registry(self.interface_registry)
        
        self._init_kernel_handlers()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _init_kernel_handlers(self) -> None:
        self._kernel_handlers = {
            "kernel:mounts.init": self._h_mounts_init,
            "kernel:registry.load": self._h_registry_load,
            "kernel:active_ecosystem.load": self._h_active_ecosystem_load,
            "kernel:interfaces.publish": self._h_interfaces_publish,
            "kernel:ir.get": self._h_ir_get,
            "kernel:ir.call": self._h_ir_call,
            "kernel:ir.register": self._h_ir_register,
            "kernel:exec_python": self._h_exec_python,
            "kernel:ctx.set": self._h_ctx_set,
            "kernel:ctx.get": self._h_ctx_get,
            "kernel:ctx.copy": self._h_ctx_copy,
            "kernel:execute_flow": self._h_execute_flow,
            "kernel:save_flow": self._h_save_flow,
            "kernel:load_flows": self._h_load_flows,
            "kernel:flow.compose": self._h_flow_compose,
            "kernel:security.init": self._h_security_init,
            "kernel:docker.check": self._h_docker_check,
            "kernel:approval.init": self._h_approval_init,
            "kernel:approval.scan": self._h_approval_scan,
            "kernel:container.init": self._h_container_init,
            "kernel:privilege.init": self._h_privilege_init,
            "kernel:api.init": self._h_api_init,
            "kernel:container.start_approved": self._h_container_start_approved,
            "kernel:component.discover": self._h_component_discover,
            "kernel:component.load": self._h_component_load,
            "kernel:emit": self._h_emit,
            "kernel:startup.failed": self._h_startup_failed,
            "kernel:vocab.load": self._h_vocab_load,
            "kernel:flow.load_all": self._h_flow_load_all,
            "kernel:flow.execute_by_id": self._h_flow_execute_by_id,
            "kernel:noop": self._h_noop,
            "kernel:python_file_call": self._h_python_file_call,
            "kernel:modifier.load_all": self._h_modifier_load_all,
            "kernel:modifier.apply": self._h_modifier_apply,
            "kernel:network.grant": self._h_network_grant,
            "kernel:network.revoke": self._h_network_revoke,
            "kernel:network.check": self._h_network_check,
            "kernel:network.list": self._h_network_list,
            "kernel:egress_proxy.start": self._h_egress_proxy_start,
            "kernel:egress_proxy.stop": self._h_egress_proxy_stop,
            "kernel:egress_proxy.status": self._h_egress_proxy_status,
            "kernel:lib.process_all": self._h_lib_process_all,
            "kernel:lib.check": self._h_lib_check,
            "kernel:lib.execute": self._h_lib_execute,
            "kernel:lib.clear_record": self._h_lib_clear_record,
            "kernel:lib.list_records": self._h_lib_list_records,
            "kernel:audit.query": self._h_audit_query,
            "kernel:audit.summary": self._h_audit_summary,
            "kernel:audit.flush": self._h_audit_flush,
            # vocab ハンドラ
            "kernel:vocab.list_groups": self._h_vocab_list_groups,
            "kernel:vocab.list_converters": self._h_vocab_list_converters,
            "kernel:vocab.summary": self._h_vocab_summary,
            "kernel:vocab.convert": self._h_vocab_convert,
            # shared_dict ハンドラ
            "kernel:shared_dict.resolve": self._h_shared_dict_resolve,
            "kernel:shared_dict.propose": self._h_shared_dict_propose,
            "kernel:shared_dict.explain": self._h_shared_dict_explain,
            "kernel:shared_dict.list": self._h_shared_dict_list,
            "kernel:shared_dict.remove": self._h_shared_dict_remove,
        }

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
        new_flow_path = Path("flows/00_startup.flow.yaml")
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
            "Using legacy flow path (flow/). This is DEPRECATED and will be removed. "
            "Please migrate to flows/00_startup.flow.yaml"
        )
        print(f"[Rumi] WARNING: {warning_msg}")
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="flow.load.fallback_warning",
            handler="kernel:flow.load",
            status="success",
            meta={"warning": warning_msg, "mode": "legacy_fallback"}
        )
        
        # 監査ログにも記録
        try:
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
        for legacy_dir in ["flow/core", "flow/ecosystem", "flow"]:
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
                    {"id": "fallback.mounts", "run": {"handler": "kernel:mounts.init", "args": {"mounts_file": "user_data/mounts.json"}}},
                    {"id": "fallback.registry", "run": {"handler": "kernel:registry.load", "args": {"ecosystem_dir": "ecosystem"}}},
                    {"id": "fallback.active", "run": {"handler": "kernel:active_ecosystem.load", "args": {"config_file": "user_data/active_ecosystem.json"}}}
                ]
            }
        }

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

    async def execute_flow(self, flow_id: str, context: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        if timeout:
            try:
                return await asyncio.wait_for(self._execute_flow_internal(flow_id, context), timeout=timeout)
            except asyncio.TimeoutError:
                return {"_error": f"Flow '{flow_id}' timed out after {timeout}s", "_flow_timeout": True}
        return await self._execute_flow_internal(flow_id, context)

    def execute_flow_sync(self, flow_id: str, context: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.execute_flow(flow_id, context, timeout)).result()
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
        handler = self.interface_registry.get(handler_key, strategy="last")
        if not handler or not callable(handler):
            return ctx, None
        resolved_args = self._resolve_value(step.get("args", {}), ctx)
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(resolved_args, ctx)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(self._executor, lambda: handler(resolved_args, ctx))
            if step.get("output"):
                ctx[step["output"]] = result
            return ctx, result
        except Exception:
            raise

    async def _execute_sub_flow_step(self, step: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        flow_name = step.get("flow")
        if not flow_name:
            return ctx, None
        
        call_stack = ctx.get("_flow_call_stack", [])
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
                ecosystem_flow_path = Path("flow/ecosystem") / f"{flow_name}.flow.yaml"
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

    def _eval_condition(self, condition: str, ctx: Dict[str, Any]) -> bool:
        condition = condition.strip()
        if " == " in condition:
            left, right = condition.split(" == ", 1)
            left_val = self._resolve_value(left.strip(), ctx)
            right_val = right.strip().strip('"\'')
            if right_val.lower() == "true":
                return left_val == True
            if right_val.lower() == "false":
                return left_val == False
            try:
                return left_val == int(right_val)
            except ValueError:
                pass
            return str(left_val) == right_val
        if " != " in condition:
            left, right = condition.split(" != ", 1)
            left_val = self._resolve_value(left.strip(), ctx)
            right_val = right.strip().strip('"\'')
            if right_val.lower() == "true":
                return left_val != True
            if right_val.lower() == "false":
                return left_val != False
            try:
                return left_val != int(right_val)
            except ValueError:
                pass
            return str(left_val) != right_val
        return bool(self._resolve_value(condition, ctx))

    def save_flow_to_file(self, flow_id: str, flow_def: Dict[str, Any], path: str = "user_data/flows") -> str:
        flow_dir = Path(path)
        flow_dir.mkdir(parents=True, exist_ok=True)
        file_path = flow_dir / f"{flow_id}.flow.json"
        file_path.write_text(json.dumps(flow_def, ensure_ascii=False, indent=2), encoding="utf-8")
        self.interface_registry.register(f"flow.{flow_id}", flow_def)
        self.diagnostics.record_step(phase="flow", step_id=f"flow.{flow_id}.save", handler="kernel:save_flow",
                                      status="success", meta={"path": str(file_path)})
        return str(file_path)

    def load_user_flows(self, path: str = "user_data/flows") -> List[str]:
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

    def on_shutdown(self, fn: Callable[[], None]) -> None:
        if callable(fn):
            self._shutdown_handlers.append(fn)

    def shutdown(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
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
            ctx["function_alias_registry"] = get_function_alias_registry()
        except Exception:
            pass
        
        try:
            ctx["flow_composer"] = get_flow_composer()
        except Exception:
            pass
        
        try:
            from .vocab_registry import get_vocab_registry
            ctx["vocab_registry"] = get_vocab_registry()
        except Exception:
            pass
        
        return ctx

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

    def _resolve_value(self, value: Any, ctx: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_value(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, ctx) for item in value]
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

    # ========== Kernel Handlers ==========

    def _h_mounts_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        mounts_file = str(args.get("mounts_file", "user_data/mounts.json"))
        try:
            from backend_core.ecosystem.mounts import DEFAULT_MOUNTS, initialize_mounts, get_mount_manager
            mf = Path(mounts_file)
            if not mf.exists():
                mf.parent.mkdir(parents=True, exist_ok=True)
                mf.write_text(json.dumps({"version": "1.0", "mounts": DEFAULT_MOUNTS}, ensure_ascii=False, indent=2), encoding="utf-8")
            initialize_mounts(config_path=str(mf))
            mm = get_mount_manager()
            ctx["mount_manager"] = mm
            self.interface_registry.register("ecosystem.mount_manager", mm, meta={"source": "kernel"})
            return mm
        except Exception as e:
            self.diagnostics.record_step(phase="startup", step_id="startup.mounts.internal", handler="kernel:mounts.init",
                                          status="failed", error=e, meta={"mounts_file": mounts_file})
            return None

    def _h_registry_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        ecosystem_dir = str(args.get("ecosystem_dir", "ecosystem"))
        try:
            import backend_core.ecosystem.registry as regmod
            from backend_core.ecosystem.registry import Registry
            reg = Registry(ecosystem_dir=ecosystem_dir)
            reg.load_all_packs()
            regmod._global_registry = reg
            ctx["registry"] = reg
            self.lifecycle.registry = reg
            self.interface_registry.register("ecosystem.registry", reg, meta={"source": "kernel"})
            return reg
        except Exception as e:
            self.diagnostics.record_step(phase="startup", step_id="startup.registry.internal", handler="kernel:registry.load",
                                          status="failed", error=e, meta={"ecosystem_dir": ecosystem_dir})
            return None

    def _h_active_ecosystem_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        config_file = str(args.get("config_file", "user_data/active_ecosystem.json"))
        try:
            import backend_core.ecosystem.active_ecosystem as amod
            from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
            mgr = ActiveEcosystemManager(config_path=config_file)
            amod._global_manager = mgr
            ctx["active_ecosystem"] = mgr
            self.lifecycle.active_ecosystem = mgr
            self.interface_registry.register("ecosystem.active_ecosystem", mgr, meta={"source": "kernel"})
            return mgr
        except Exception as e:
            self.diagnostics.record_step(phase="startup", step_id="startup.active_ecosystem.internal", handler="kernel:active_ecosystem.load",
                                          status="failed", error=e, meta={"config_file": config_file})
            return None

    def _h_interfaces_publish(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        self.interface_registry.register("kernel.state", {"services_ready": True, "ts": self._now_ts()}, meta={"source": "kernel"})
        return {"services_ready": True}

    def _h_ir_get(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        key = args.get("key")
        if not key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'key' argument"}}
        strategy = args.get("strategy", "last")
        value = self.interface_registry.get(key, strategy=strategy)
        if args.get("store_as"):
            ctx[args["store_as"]] = value
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"key": key, "strategy": strategy, "found": value is not None}, "value": value}

    def _h_ir_call(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        key = args.get("key")
        if not key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'key' argument"}}
        fn = self.interface_registry.get(key, strategy=args.get("strategy", "last"))
        if fn is None:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "not_found", "key": key}}
        if not callable(fn):
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "not_callable", "key": key}}
        resolved_args = self._resolve_args(args.get("call_args", {}), ctx)
        try:
            result = fn(ctx) if args.get("pass_ctx", False) else (fn(**resolved_args) if resolved_args else fn())
        except TypeError:
            try:
                result = fn(ctx)
            except Exception as e:
                return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e), "key": key}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e), "key": key}}
        if args.get("store_as"):
            ctx[args["store_as"]] = result
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"key": key, "has_result": result is not None}, "result": result}

    def _h_ir_register(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        key = args.get("key")
        if not key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'key' argument"}}
        value = ctx.get(args["value_from_ctx"]) if args.get("value_from_ctx") else (self._resolve_value(args.get("value"), ctx) if args.get("value") is not None else None)
        self.interface_registry.register(key, value, meta=args.get("meta", {}))
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"key": key, "has_value": value is not None}}

    def _h_exec_python(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        file_arg = args.get("file")
        if not file_arg:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'file' argument"}}
        base_path = args.get("base_path") or ctx.get("_foreach_current_path", ".")
        full_path = Path(base_path) / file_arg if base_path and base_path != "." else Path(file_arg)
        if not full_path.exists():
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "file_not_found", "path": str(full_path)}}
        phase = args.get("phase", "exec")
        exec_ctx = {"phase": phase, "ts": self._now_ts(), "paths": {"file": str(full_path), "dir": str(full_path.parent), "component_runtime_dir": str(full_path.parent)},
                    "ids": ctx.get("_foreach_ids", {}), "interface_registry": self.interface_registry, "event_bus": self.event_bus,
                    "diagnostics": self.diagnostics, "install_journal": self.install_journal}
        for k, v in args.get("inject", {}).items():
            exec_ctx[k] = self._resolve_value(v, ctx)
        try:
            self.lifecycle._exec_python_file(full_path, exec_ctx)
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"file": str(full_path), "phase": phase}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e), "file": str(full_path), "phase": phase}}

    def _h_ctx_set(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        key = args.get("key")
        if not key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'key' argument"}}
        ctx[key] = self._resolve_value(args.get("value"), ctx)
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"key": key}}

    def _h_ctx_get(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        key = args.get("key")
        if not key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'key' argument"}}
        value = ctx.get(key, args.get("default"))
        if args.get("store_as"):
            ctx[args["store_as"]] = value
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"key": key, "found": key in ctx}, "value": value}

    def _h_ctx_copy(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        from_key, to_key = args.get("from_key"), args.get("to_key")
        if not from_key or not to_key:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'from_key' or 'to_key' argument"}}
        ctx[to_key] = ctx.get(from_key)
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"from_key": from_key, "to_key": to_key}}

    def _h_execute_flow(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        flow_id = args.get("flow_id")
        if not flow_id:
            return {"_error": "missing flow_id"}
        flow_ctx = args.get("context", {})
        if ctx.get("_flow_execution_id"):
            flow_ctx["_parent_flow_execution_id"] = ctx["_flow_execution_id"]
        return self.execute_flow_sync(flow_id, flow_ctx, args.get("timeout"))

    def _h_save_flow(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        flow_id, flow_def = args.get("flow_id"), args.get("flow_def")
        if not flow_id or not flow_def:
            return {"_error": "missing flow_id or flow_def"}
        return {"path": self.save_flow_to_file(flow_id, flow_def, args.get("path", "user_data/flows"))}

    def _h_load_flows(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        return {"loaded": self.load_user_flows(args.get("path", "user_data/flows"))}

    def _h_flow_compose(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            composer = get_flow_composer()
            alias_registry = get_function_alias_registry()
            composer.set_alias_registry(alias_registry)
            
            modifiers = composer.collect_modifiers(self.interface_registry)
            
            if not modifiers:
                return {
                    "_kernel_step_status": "skipped",
                    "_kernel_step_meta": {"reason": "no_modifiers"}
                }
            
            capabilities = {}
            all_caps = self.interface_registry.get("component.capabilities", strategy="all") or []
            for cap_dict in all_caps:
                if isinstance(cap_dict, dict):
                    capabilities.update(cap_dict)
            
            if self._flow:
                self._flow = composer.apply_modifiers(
                    self._flow,
                    modifiers,
                    self.interface_registry,
                    capabilities
                )
            
            applied = composer.get_applied_modifiers()
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="flow.compose.complete",
                handler="kernel:flow.compose",
                status="success",
                meta={
                    "modifiers_collected": len(modifiers),
                    "modifiers_applied": len(applied),
                    "applied_ids": [m.get("id") for m in applied]
                }
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "modifiers_collected": len(modifiers),
                    "modifiers_applied": len(applied)
                }
            }
            
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="flow.compose.error",
                handler="kernel:flow.compose",
                status="failed",
                error=e
            )
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_security_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            ctx["_security_initialized"] = True
            ctx["_strict_mode"] = args.get("strict_mode", True)
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="security.init",
                handler="kernel:security.init",
                status="success",
                meta={"strict_mode": ctx["_strict_mode"]}
            )
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_docker_check(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        required = args.get("required", True)
        timeout = args.get("timeout_seconds", 10)
        
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=timeout
            )
            available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            available = False
        
        ctx["_docker_available"] = available
        
        if required and not available:
            self.diagnostics.record_step(
                phase="startup",
                step_id="docker.check",
                handler="kernel:docker.check",
                status="failed",
                error={"type": "DockerNotAvailable", "message": "Docker is required but not available"},
                meta={"required": required}
            )
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Docker not available"}}
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="docker.check",
            handler="kernel:docker.check",
            status="success",
            meta={"available": available, "required": required}
        )
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"docker_available": available}}

    def _h_approval_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .approval_manager import initialize_approval_manager, get_approval_manager
            initialize_approval_manager()
            am = get_approval_manager()
            ctx["approval_manager"] = am
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="approval.init",
                handler="kernel:approval.init",
                status="success"
            )
            return {"_kernel_step_status": "success"}
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="approval.init",
                handler="kernel:approval.init",
                status="failed",
                error=e
            )
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_approval_scan(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .approval_manager import get_approval_manager
            am = get_approval_manager()
            
            packs = am.scan_packs()
            check_hash = args.get("check_hash", True)
            
            modified = []
            pending = []
            approved = []
            
            for pack_id in packs:
                status = am.get_status(pack_id)
                if status:
                    status_str = status.value if hasattr(status, 'value') else str(status)
                    if status_str == "approved":
                        if check_hash and not am.verify_hash(pack_id):
                            am.mark_modified(pack_id)
                            modified.append(pack_id)
                        else:
                            approved.append(pack_id)
                    elif status_str in ("installed", "pending"):
                        pending.append(pack_id)
                    elif status_str == "modified":
                        modified.append(pack_id)
            
            ctx["_packs_approved"] = approved
            ctx["_packs_pending"] = pending
            ctx["_packs_modified"] = modified
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="approval.scan",
                handler="kernel:approval.scan",
                status="success",
                meta={
                    "total": len(packs),
                    "approved": len(approved),
                    "pending": len(pending),
                    "modified": len(modified)
                }
            )
            return {"_kernel_step_status": "success", "_kernel_step_meta": {
                "approved": approved, "pending": pending, "modified": modified
            }}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_container_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .container_orchestrator import initialize_container_orchestrator, get_container_orchestrator
            initialize_container_orchestrator()
            co = get_container_orchestrator()
            ctx["container_orchestrator"] = co
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="container.init",
                handler="kernel:container.init",
                status="success"
            )
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_privilege_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .host_privilege_manager import initialize_host_privilege_manager, get_host_privilege_manager
            initialize_host_privilege_manager()
            hpm = get_host_privilege_manager()
            ctx["host_privilege_manager"] = hpm
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="privilege.init",
                handler="kernel:privilege.init",
                status="success"
            )
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_api_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .pack_api_server import initialize_pack_api_server
            
            host = args.get("host", "127.0.0.1")
            port = args.get("port", 8765)
            
            api_server = initialize_pack_api_server(
                host=host,
                port=port,
                approval_manager=ctx.get("approval_manager"),
                container_orchestrator=ctx.get("container_orchestrator"),
                host_privilege_manager=ctx.get("host_privilege_manager")
            )
            ctx["pack_api_server"] = api_server
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="api.init",
                handler="kernel:api.init",
                status="success",
                meta={"host": host, "port": port}
            )
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_container_start_approved(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        approved = ctx.get("_packs_approved", [])
        if not approved:
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"started": 0}}
        
        co = ctx.get("container_orchestrator")
        if not co:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "no_orchestrator"}}
        
        started = []
        failed = []
        timeout = args.get("timeout_per_pack", 30)
        
        for pack_id in approved:
            try:
                result = co.start_container(pack_id, timeout=timeout)
                if result.success:
                    started.append(pack_id)
                else:
                    failed.append({"pack_id": pack_id, "error": result.error})
            except Exception as e:
                failed.append({"pack_id": pack_id, "error": str(e)})
        
        ctx["_containers_started"] = started
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="container.start_approved",
            handler="kernel:container.start_approved",
            status="success" if not failed else "partial",
            meta={"started": len(started), "failed": len(failed)}
        )
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"started": started, "failed": failed}}

    def _h_component_discover(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        approved_only = args.get("approved_only", True)
        approved = ctx.get("_packs_approved", [])
        
        try:
            from backend_core.ecosystem.registry import get_registry
            reg = get_registry()
            
            components = []
            for comp in reg.get_all_components():
                pack_id = getattr(comp, "pack_id", None)
                if approved_only and pack_id not in approved:
                    continue
                components.append({
                    "full_id": getattr(comp, "full_id", None),
                    "pack_id": pack_id,
                    "type": getattr(comp, "type", None),
                    "id": getattr(comp, "id", None)
                })
            
            ctx["_discovered_components"] = components
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="component.discover",
                handler="kernel:component.discover",
                status="success",
                meta={"count": len(components), "approved_only": approved_only}
            )
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"count": len(components)}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_component_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        container_execution = args.get("container_execution", True)
        components = ctx.get("_discovered_components", [])
        
        if not components:
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"loaded": 0}}
        
        self.lifecycle.run_phase("setup")
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="component.load",
            handler="kernel:component.load",
            status="success",
            meta={"container_execution": container_execution}
        )
        return {"_kernel_step_status": "success"}

    def _h_emit(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        event = args.get("event", "")
        if event and self.event_bus:
            self.event_bus.publish(event, {"ts": self._now_ts()})
        return {"_kernel_step_status": "success"}

    def _h_startup_failed(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        pending = ctx.get("_packs_pending", [])
        modified = ctx.get("_packs_modified", [])
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="startup.failed",
            handler="kernel:startup.failed",
            status="failed",
            meta={
                "pending_approvals": pending,
                "modified_packs": modified,
                "message": "Startup failed. Check pending approvals or Docker availability."
            }
        )
        return {"_kernel_step_status": "success"}

    def _h_vocab_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            
            file_path = args.get("file")
            pack_id = args.get("pack_id")
            
            if file_path:
                from pathlib import Path
                count = vr.load_vocab_file(Path(file_path), pack_id)
                return {"_kernel_step_status": "success", "_kernel_step_meta": {"groups_loaded": count}}
            
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "no_file"}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_flow_load_all(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        全Flowファイルをロードし、modifierを適用し、InterfaceRegistryに登録
        
        flows/(公式)と ecosystem/flows/(エコシステム)から読み込む
        """
        try:
            # 1. Flowをロード
            loader = get_flow_loader()
            flows = loader.load_all_flows()
            
            # Flowロードエラーを記録
            flow_errors = loader.get_load_errors()
            for err in flow_errors:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="flow.load.error",
                    handler="kernel:flow.load_all",
                    status="failed",
                    error={"errors": err.get("errors", [])},
                    meta={"file": err.get("file")}
                )
            
            # 2. modifierをロード
            modifier_loader = get_modifier_loader()
            all_modifiers = modifier_loader.load_all_modifiers()
            
            # modifierロードエラーを記録
            modifier_errors = modifier_loader.get_load_errors()
            for err in modifier_errors:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="modifier.load.error",
                    handler="kernel:flow.load_all",
                    status="failed",
                    error={"errors": err.get("errors", [])},
                    meta={"file": err.get("file")}
                )
            
            # 3. 各Flowにmodifierを適用してIRに登録
            registered = []
            modifier_results_all = []
            
            applier = get_modifier_applier()
            applier.set_interface_registry(self.interface_registry)
            
            for flow_id, flow_def in flows.items():
                # このFlowに対するmodifierを取得
                modifiers_for_flow = modifier_loader.get_modifiers_for_flow(flow_id)
                
                # modifier適用
                if modifiers_for_flow:
                    modified_flow, results = applier.apply_modifiers(flow_def, modifiers_for_flow)
                    modifier_results_all.extend(results)
                    
                    # 適用結果をログ
                    for result in results:
                        if result.success:
                            self.diagnostics.record_step(
                                phase="startup",
                                step_id=f"modifier.apply.{result.modifier_id}",
                                handler="kernel:flow.load_all",
                                status="success",
                                meta={
                                    "action": result.action,
                                    "target_flow": flow_id,
                                    "target_step_id": result.target_step_id
                                }
                            )
                        elif result.skipped_reason:
                            self.diagnostics.record_step(
                                phase="startup",
                                step_id=f"modifier.apply.{result.modifier_id}",
                                handler="kernel:flow.load_all",
                                status="skipped",
                                meta={
                                    "reason": result.skipped_reason,
                                    "target_flow": flow_id
                                }
                            )
                        else:
                            self.diagnostics.record_step(
                                phase="startup",
                                step_id=f"modifier.apply.{result.modifier_id}",
                                handler="kernel:flow.load_all",
                                status="failed",
                                error={"errors": result.errors},
                                meta={"target_flow": flow_id}
                            )
                    
                    final_flow = modified_flow
                    applied_modifiers = [r.modifier_id for r in results if r.success]
                else:
                    final_flow = flow_def
                    applied_modifiers = []
                
                # 4. IRに登録(1回のみ)
                converted = self._convert_new_flow_to_legacy(final_flow)
                ir_key = f"flow.{flow_id}"
                self.interface_registry.register(ir_key, converted, meta={
                    "_source_file": str(final_flow.source_file) if final_flow.source_file else None,
                    "_source_type": final_flow.source_type,
                    "_flow_loader": True,
                    "_modifiers_applied": applied_modifiers,
                })
                registered.append(flow_id)
            
            # 5. 完了ログ
            modifier_success = sum(1 for r in modifier_results_all if r.success)
            modifier_skipped = sum(1 for r in modifier_results_all if r.skipped_reason)
            modifier_failed = sum(1 for r in modifier_results_all if not r.success and not r.skipped_reason)
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="flow.load_all.complete",
                handler="kernel:flow.load_all",
                status="success",
                meta={
                    "flows_registered": len(registered),
                    "flow_ids": registered,
                    "flow_errors": len(flow_errors),
                    "modifiers_loaded": len(all_modifiers),
                    "modifiers_applied": modifier_success,
                    "modifiers_skipped": modifier_skipped,
                    "modifiers_failed": modifier_failed,
                }
            )
            
            # 監査ログに記録
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="flow_load_all",
                success=True,
                details={
                    "flows_registered": len(registered),
                    "flow_ids": registered,
                    "modifiers_loaded": len(all_modifiers),
                    "modifiers_applied": modifier_success,
                }
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "flows_registered": registered,
                    "flow_error_count": len(flow_errors),
                    "modifiers_loaded": len(all_modifiers),
                    "modifiers_applied": modifier_success,
                    "modifiers_skipped": modifier_skipped,
                }
            }
            
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="flow.load_all.failed",
                handler="kernel:flow.load_all",
                status="failed",
                error=e
            )
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_flow_execute_by_id(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        flow_idを指定してFlowを実行
        
        Args:
            flow_id: 実行するFlow ID（必須）
            inputs: Flow入力（任意）
            timeout: タイムアウト秒数（任意）
            resolve: 共有辞書で解決するか（任意、デフォルトFalse）
            resolve_namespace: 解決に使用するnamespace（任意、デフォルト"flow_id"）
        """
        flow_id = args.get("flow_id")
        if not flow_id:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing flow_id"}}
        
        inputs = args.get("inputs", {})
        timeout = args.get("timeout")
        resolve = args.get("resolve", False)
        resolve_namespace = args.get("resolve_namespace", "flow_id")
        
        # 共有辞書での解決（オプトイン）
        original_flow_id = flow_id
        resolved_flow_id = flow_id
        resolution_info = None
        
        if resolve:
            try:
                from .shared_dict import get_shared_dict_resolver
                resolver = get_shared_dict_resolver()
                result = resolver.resolve_chain(resolve_namespace, flow_id, ctx)
                resolved_flow_id = result.resolved
                
                resolution_info = {
                    "original": original_flow_id,
                    "resolved": resolved_flow_id,
                    "hops": result.hops,
                    "cycle_detected": result.cycle_detected,
                    "max_hops_reached": result.max_hops_reached,
                }
                
                # 解決された場合は監査ログに記録
                if resolved_flow_id != original_flow_id:
                    try:
                        audit = get_audit_logger()
                        audit.log_system_event(
                            event_type="flow_id_resolved",
                            success=True,
                            details={
                                "namespace": resolve_namespace,
                                "original": original_flow_id,
                                "resolved": resolved_flow_id,
                                "hops": result.hops,
                            }
                        )
                    except Exception:
                        pass
                    
                    self.diagnostics.record_step(
                        phase="flow",
                        step_id=f"flow.{original_flow_id}.resolved",
                        handler="kernel:flow.execute_by_id",
                        status="success",
                        meta={
                            "original_flow_id": original_flow_id,
                            "resolved_flow_id": resolved_flow_id,
                            "namespace": resolve_namespace,
                        }
                    )
            except Exception as e:
                # 解決失敗時は元のflow_idを使用
                self.diagnostics.record_step(
                    phase="flow",
                    step_id=f"flow.{original_flow_id}.resolve_failed",
                    handler="kernel:flow.execute_by_id",
                    status="failed",
                    error=e,
                    meta={"namespace": resolve_namespace}
                )
        
        # Flow実行
        exec_ctx = dict(ctx)
        exec_ctx.update(inputs)
        
        if resolution_info:
            exec_ctx["_flow_resolution"] = resolution_info
        
        result = self.execute_flow_sync(resolved_flow_id, exec_ctx, timeout)
        
        return {
            "_kernel_step_status": "success" if "_error" not in result else "failed",
            "_kernel_step_meta": {
                "flow_id": resolved_flow_id,
                "original_flow_id": original_flow_id if resolve else None,
                "resolved": resolve and (resolved_flow_id != original_flow_id),
            },
            "result": result
        }

    def _h_noop(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """何もしないハンドラ(プレースホルダー)"""
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"handler": "noop"}}

    def _convert_new_flow_to_legacy(self, flow_def: FlowDefinition) -> Dict[str, Any]:
        """
        新形式FlowDefinitionを既存Kernelが処理できる形式に変換
        
        新形式: phases, inputs, outputs, steps(type: python_file_call等)
        既存形式: steps(handler, args, when, output)
        """
        legacy_steps = []
        
        for step in flow_def.steps:
            legacy_step = {
                "id": step.id,
                "phase": step.phase,
                "priority": step.priority,
            }
            
            # whenの変換
            if step.when:
                legacy_step["when"] = step.when
            
            # outputの変換
            if step.output:
                legacy_step["output"] = step.output
            
            # typeごとの変換
            if step.type == "python_file_call":
                legacy_step["handler"] = "kernel:python_file_call"
                legacy_step["args"] = {
                    "file": step.file,
                    "owner_pack": step.owner_pack,
                    "input": step.input,
                    "timeout_seconds": step.timeout_seconds,
                    "_step_id": step.id,
                    "_phase": step.phase,
                }
                if step.output:
                    legacy_step["output"] = step.output
            elif step.type == "set":
                # set: コンテキストに値を設定
                legacy_step["handler"] = "kernel:ctx.set"
                if isinstance(step.input, dict):
                    legacy_step["args"] = {
                        "key": step.input.get("key", step.output or ""),
                        "value": step.input.get("value"),
                    }
                else:
                    legacy_step["args"] = {"key": step.output or "", "value": step.input}
            elif step.type == "if":
                # if: 条件分岐(簡易版)
                legacy_step["handler"] = "kernel:noop"
                if isinstance(step.input, dict):
                    legacy_step["when"] = step.input.get("condition", "false")
            elif step.type == "handler":
                # handler: 既存のIRハンドラを呼び出し
                if isinstance(step.input, dict):
                    legacy_step["handler"] = step.input.get("handler", "kernel:noop")
                    legacy_step["args"] = step.input.get("args", {})
                else:
                    legacy_step["handler"] = str(step.input) if step.input else "kernel:noop"
                    legacy_step["args"] = {}
            else:
                # 未知のtype: noopとして扱い、警告を記録
                legacy_step["handler"] = "kernel:noop"
                legacy_step["args"] = {"_unknown_type": step.type, "_raw": step.raw}
            
            legacy_steps.append(legacy_step)
        
        return {
            "flow_id": flow_def.flow_id,
            "inputs": flow_def.inputs,
            "outputs": flow_def.outputs,
            "phases": flow_def.phases,
            "defaults": flow_def.defaults,
            "steps": legacy_steps,
            "_source_file": str(flow_def.source_file) if flow_def.source_file else None,
            "_source_type": flow_def.source_type,
        }

    def _h_python_file_call(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        python_file_call ステップを実行
        
        Args (from args):
            file: 実行するファイルパス(必須)
            owner_pack: 所有Pack ID(任意、パスから推測可能)
            input: 入力データ(任意)
            timeout_seconds: タイムアウト秒数(任意、デフォルト60)
            _step_id: ステップID(内部用)
            _phase: フェーズ名(内部用)
        """
        import sys
        
        file_path = args.get("file")
        if not file_path:
            self.diagnostics.record_step(
                phase=args.get("_phase", "flow"),
                step_id=args.get("_step_id", "unknown"),
                handler="kernel:python_file_call",
                status="failed",
                error={"type": "missing_file", "message": "No 'file' specified"}
            )
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "No 'file' specified"}
            }
        
        owner_pack = args.get("owner_pack")
        input_data = args.get("input", {})
        timeout_seconds = args.get("timeout_seconds", 60.0)
        step_id = args.get("_step_id", "unknown")
        phase = args.get("_phase", "flow")
        
        # 入力データの変数解決
        resolved_input = self._resolve_value(input_data, ctx)
        
        # 実行コンテキストを構築
        exec_context = ExecutionContext(
            flow_id=ctx.get("_flow_id", "unknown"),
            step_id=step_id,
            phase=phase,
            ts=self._now_ts(),
            owner_pack=owner_pack,
            inputs=resolved_input,
            diagnostics_callback=lambda data: self.diagnostics.record_step(
                phase=data.get("phase", phase),
                step_id=f"{step_id}.{data.get('type', 'event')}",
                handler="kernel:python_file_call",
                status="failed" if "error" in data else "success",
                error=data.get("error"),
                meta=data
            )
        )
        
        # 実行
        executor = get_python_file_executor()
        result = executor.execute(
            file_path=file_path,
            owner_pack=owner_pack,
            input_data=resolved_input,
            context=exec_context,
            timeout_seconds=timeout_seconds
        )
        
        # 結果を記録
        status = "success" if result.success else "failed"
        self.diagnostics.record_step(
            phase=phase,
            step_id=step_id,
            handler="kernel:python_file_call",
            status=status,
            error={"type": result.error_type, "message": result.error} if result.error else None,
            meta={
                "file": file_path,
                "owner_pack": owner_pack,
                "execution_mode": result.execution_mode,
                "execution_time_ms": result.execution_time_ms,
                "warnings": result.warnings if result.warnings else None,
            }
        )
        
        # 警告をログ出力
        for warning in result.warnings:
            print(f"[python_file_call] WARNING: {warning}", file=sys.stderr)
        
        if result.success:
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "execution_mode": result.execution_mode,
                    "execution_time_ms": result.execution_time_ms,
                },
                "output": result.output
            }
        else:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {
                    "error": result.error,
                    "error_type": result.error_type,
                    "execution_mode": result.execution_mode,
                }
            }

    def _h_modifier_load_all(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """全modifierファイルをロード(単独実行用)"""
        try:
            loader = get_modifier_loader()
            modifiers = loader.load_all_modifiers()
            
            errors = loader.get_load_errors()
            for err in errors:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="modifier.load.error",
                    handler="kernel:modifier.load_all",
                    status="failed",
                    error={"errors": err.get("errors", [])},
                    meta={"file": err.get("file")}
                )
            
            self.diagnostics.record_step(
                phase="startup",
                step_id="modifier.load_all.complete",
                handler="kernel:modifier.load_all",
                status="success",
                meta={
                    "loaded_count": len(modifiers),
                    "modifier_ids": list(modifiers.keys()),
                    "error_count": len(errors)
                }
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "loaded": list(modifiers.keys()),
                    "error_count": len(errors)
                }
            }
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="modifier.load_all.failed",
                handler="kernel:modifier.load_all",
                status="failed",
                error=e
            )
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_modifier_apply(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """指定Flowにmodifierを再適用(単独実行用)"""
        try:
            target_flow_id = args.get("flow_id")
            
            flow_loader = get_flow_loader()
            modifier_loader = get_modifier_loader()
            applier = get_modifier_applier()
            applier.set_interface_registry(self.interface_registry)
            
            flows = flow_loader.get_loaded_flows()
            all_results = []
            
            for flow_id, flow_def in flows.items():
                if target_flow_id and flow_id != target_flow_id:
                    continue
                
                modifiers = modifier_loader.get_modifiers_for_flow(flow_id)
                if not modifiers:
                    continue
                
                modified_flow, results = applier.apply_modifiers(flow_def, modifiers)
                all_results.extend(results)
                
                # IRを更新
                converted = self._convert_new_flow_to_legacy(modified_flow)
                self.interface_registry.register(f"flow.{flow_id}", converted, meta={
                    "_source_file": str(modified_flow.source_file) if modified_flow.source_file else None,
                    "_source_type": modified_flow.source_type,
                    "_flow_loader": True,
                    "_modifiers_applied": [r.modifier_id for r in results if r.success],
                })
            
            success_count = sum(1 for r in all_results if r.success)
            skip_count = sum(1 for r in all_results if r.skipped_reason)
            fail_count = sum(1 for r in all_results if not r.success and not r.skipped_reason)
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "success_count": success_count,
                    "skip_count": skip_count,
                    "fail_count": fail_count
                }
            }
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_network_grant(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """ネットワークアクセスを許可"""
        pack_id = args.get("pack_id")
        if not pack_id:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing pack_id"}}
        
        allowed_domains = args.get("allowed_domains", [])
        allowed_ports = args.get("allowed_ports", [])
        
        if not allowed_domains and not allowed_ports:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Must specify allowed_domains or allowed_ports"}}
        
        try:
            ngm = get_network_grant_manager()
            grant = ngm.grant_network_access(
                pack_id=pack_id,
                allowed_domains=allowed_domains,
                allowed_ports=allowed_ports,
                granted_by=args.get("granted_by", "kernel"),
                notes=args.get("notes", "")
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"pack_id": pack_id},
                "grant": grant.to_dict()
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_network_revoke(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """ネットワークアクセスを取り消し"""
        pack_id = args.get("pack_id")
        if not pack_id:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing pack_id"}}
        
        try:
            ngm = get_network_grant_manager()
            success = ngm.revoke_network_access(pack_id=pack_id, reason=args.get("reason", ""))
            return {
                "_kernel_step_status": "success" if success else "failed",
                "_kernel_step_meta": {"pack_id": pack_id, "revoked": success}
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_network_check(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """ネットワークアクセスをチェック"""
        pack_id = args.get("pack_id")
        domain = args.get("domain")
        port = args.get("port")
        
        if not pack_id or not domain or port is None:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing pack_id, domain, or port"}}
        
        try:
            ngm = get_network_grant_manager()
            result = ngm.check_access(pack_id, domain, int(port))
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"allowed": result.allowed, "reason": result.reason},
                "result": {"allowed": result.allowed, "reason": result.reason, "pack_id": result.pack_id, "domain": result.domain, "port": result.port}
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_network_list(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """全ネットワークGrantを一覧"""
        try:
            ngm = get_network_grant_manager()
            grants = ngm.get_all_grants()
            disabled = ngm.get_disabled_packs()
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"grant_count": len(grants), "disabled_count": len(disabled)},
                "grants": {k: v.to_dict() for k, v in grants.items()},
                "disabled_packs": list(disabled)
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_egress_proxy_start(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """Egress Proxyを起動"""
        try:
            ngm = get_network_grant_manager()
            audit = get_audit_logger()
            proxy = initialize_egress_proxy(
                host=args.get("host"), port=args.get("port"),
                network_grant_manager=ngm, audit_logger=audit, auto_start=True
            )
            if proxy.is_running():
                return {"_kernel_step_status": "success", "_kernel_step_meta": {"endpoint": proxy.get_endpoint(), "running": True}}
            else:
                return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Failed to start proxy"}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_egress_proxy_stop(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """Egress Proxyを停止"""
        try:
            shutdown_egress_proxy()
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_egress_proxy_status(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """Egress Proxyの状態を取得"""
        try:
            proxy = get_egress_proxy()
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"running": proxy.is_running(), "endpoint": proxy.get_endpoint() if proxy.is_running() else None}
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_lib_process_all(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """全Packのlibを処理"""
        try:
            packs_dir = Path(args.get("packs_dir", "ecosystem/packs"))
            executor = get_lib_executor()
            results = executor.process_all_packs(packs_dir, ctx)
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"installed": results["installed"], "updated": results["updated"], "failed_count": len(results["failed"])}, "results": results}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_lib_check(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """Packのlib実行が必要かチェック"""
        pack_id = args.get("pack_id")
        if not pack_id:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing pack_id"}}
        pack_dir = Path(args.get("pack_dir", f"ecosystem/packs/{pack_id}"))
        try:
            executor = get_lib_executor()
            result = executor.check_pack(pack_id, pack_dir)
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"needs_install": result.needs_install, "needs_update": result.needs_update, "reason": result.reason}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_lib_execute(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """Packのlibを手動実行"""
        pack_id = args.get("pack_id")
        lib_type = args.get("lib_type")
        if not pack_id or not lib_type:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing pack_id or lib_type"}}
        if lib_type not in ("install", "update"):
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "lib_type must be 'install' or 'update'"}}
        pack_dir = Path(args.get("pack_dir", f"ecosystem/packs/{pack_id}"))
        try:
            executor = get_lib_executor()
            lib_dir = pack_dir / "backend" / "lib"
            if not lib_dir.exists():
                lib_dir = pack_dir / "lib"
            lib_file = lib_dir / f"{lib_type}.py"
            if not lib_file.exists():
                return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": f"File not found: {lib_file}"}}
            result = executor.execute_lib(pack_id, lib_file, lib_type, ctx)
            return {"_kernel_step_status": "success" if result.success else "failed", "_kernel_step_meta": {"pack_id": pack_id, "lib_type": lib_type, "success": result.success, "error": result.error}, "output": result.output}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_lib_clear_record(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """lib実行記録をクリア"""
        try:
            executor = get_lib_executor()
            pack_id = args.get("pack_id")
            if pack_id:
                success = executor.clear_record(pack_id)
                return {"_kernel_step_status": "success" if success else "failed", "_kernel_step_meta": {"pack_id": pack_id, "cleared": success}}
            else:
                count = executor.clear_all_records()
                return {"_kernel_step_status": "success", "_kernel_step_meta": {"cleared_count": count}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_lib_list_records(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """lib実行記録を一覧"""
        try:
            executor = get_lib_executor()
            records = executor.get_all_records()
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"count": len(records)}, "records": {pack_id: record.to_dict() for pack_id, record in records.items()}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_audit_query(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """監査ログを検索"""
        try:
            audit = get_audit_logger()
            results = audit.query_logs(
                category=args.get("category"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
                pack_id=args.get("pack_id"),
                flow_id=args.get("flow_id"),
                success_only=args.get("success_only"),
                limit=args.get("limit", 100)
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"count": len(results)},
                "results": results
            }
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_audit_summary(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """監査ログのサマリーを取得"""
        try:
            audit = get_audit_logger()
            summary = audit.get_summary(
                category=args.get("category"),
                date=args.get("date")
            )
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": summary,
                "summary": summary
            }
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    def _h_audit_flush(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """監査ログバッファをフラッシュ"""
        try:
            audit = get_audit_logger()
            audit.flush()
            
            return {"_kernel_step_status": "success"}
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": str(e)}
            }

    # ========== vocab ハンドラ ==========

    def _h_vocab_list_groups(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """登録された同義語グループを一覧"""
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            groups = vr.list_groups()
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"count": len(groups)},
                "groups": groups
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_vocab_list_converters(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """登録されたconverterを一覧"""
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            converters = vr.list_converters()
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"count": len(converters)},
                "converters": converters
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_vocab_summary(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """vocab/converterの登録状況サマリーを取得"""
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            summary = vr.get_registration_summary()
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": summary.get("totals", {}),
                "summary": summary
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_vocab_convert(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """データを変換"""
        from_term = args.get("from_term")
        to_term = args.get("to_term")
        data = args.get("data")
        log_success = args.get("log_success", False)
        
        if not from_term or not to_term:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing from_term or to_term"}}
        
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            result, success = vr.convert(from_term, to_term, data, log_success=log_success)
            return {
                "_kernel_step_status": "success" if success else "failed",
                "_kernel_step_meta": {"converted": success, "from": from_term, "to": to_term},
                "result": result
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    # ========== shared_dict ハンドラ ==========

    def _h_shared_dict_resolve(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """共有辞書でtokenを解決"""
        namespace = args.get("namespace")
        token = args.get("token")
        
        if not namespace or not token:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing namespace or token"}}
        
        try:
            from .shared_dict import get_shared_dict_resolver
            resolver = get_shared_dict_resolver()
            result = resolver.resolve_chain(namespace, token, ctx)
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "original": result.original,
                    "resolved": result.resolved,
                    "hop_count": len(result.hops),
                    "cycle_detected": result.cycle_detected,
                    "max_hops_reached": result.max_hops_reached,
                },
                "resolved": result.resolved,
                "hops": result.hops,
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_shared_dict_propose(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """共有辞書にルールを提案"""
        namespace = args.get("namespace")
        token = args.get("token")
        value = args.get("value")
        provenance = args.get("provenance", {})
        
        if not namespace or not token or value is None:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing namespace, token, or value"}}
        
        try:
            from .shared_dict import get_shared_dict_journal
            journal = get_shared_dict_journal()
            result = journal.propose(namespace, token, value, provenance)
            
            return {
                "_kernel_step_status": "success" if result.accepted else "failed",
                "_kernel_step_meta": {
                    "status": result.status.value,
                    "accepted": result.accepted,
                    "reason": result.reason,
                },
                "result": {
                    "status": result.status.value,
                    "namespace": result.namespace,
                    "token": result.token,
                    "value": result.value,
                    "reason": result.reason,
                }
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_shared_dict_explain(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """共有辞書の解決を説明"""
        namespace = args.get("namespace")
        token = args.get("token")
        
        if not namespace or not token:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing namespace or token"}}
        
        try:
            from .shared_dict import get_shared_dict_resolver
            resolver = get_shared_dict_resolver()
            result = resolver.explain(namespace, token, ctx)
            
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {
                    "original": result.original,
                    "resolved": result.resolved,
                    "hop_count": len(result.hops),
                },
                "explanation": {
                    "original": result.original,
                    "resolved": result.resolved,
                    "hops": result.hops,
                    "cycle_detected": result.cycle_detected,
                    "max_hops_reached": result.max_hops_reached,
                }
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_shared_dict_list(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """共有辞書のnamespace/ルールを一覧"""
        namespace = args.get("namespace")
        
        try:
            from .shared_dict import get_shared_dict_resolver
            resolver = get_shared_dict_resolver()
            
            if namespace:
                rules = resolver.list_rules(namespace)
                return {
                    "_kernel_step_status": "success",
                    "_kernel_step_meta": {"namespace": namespace, "rule_count": len(rules)},
                    "rules": rules,
                }
            else:
                namespaces = resolver.list_namespaces()
                return {
                    "_kernel_step_status": "success",
                    "_kernel_step_meta": {"namespace_count": len(namespaces)},
                    "namespaces": namespaces,
                }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}

    def _h_shared_dict_remove(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """共有辞書からルールを削除"""
        namespace = args.get("namespace")
        token = args.get("token")
        provenance = args.get("provenance", {})
        
        if not namespace or not token:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Missing namespace or token"}}
        
        try:
            from .shared_dict import get_shared_dict_journal
            journal = get_shared_dict_journal()
            success = journal.remove(namespace, token, provenance)
            
            return {
                "_kernel_step_status": "success" if success else "failed",
                "_kernel_step_meta": {"removed": success, "namespace": namespace, "token": token},
            }
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e)}}
