"""
kernel.py - Flow Runner(用途非依存カーネル)
async対応、Flow Hook、タイムアウト、循環検出対応版
"""

from __future__ import annotations

import json
import asyncio
import uuid
import importlib.util
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
        self._init_kernel_handlers()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _init_kernel_handlers(self) -> None:
        self._kernel_handlers = {
            "kernel:mounts.init": self._h_mounts_init, "kernel:registry.load": self._h_registry_load,
            "kernel:active_ecosystem.load": self._h_active_ecosystem_load, "kernel:interfaces.publish": self._h_interfaces_publish,
            "kernel:ir.get": self._h_ir_get, "kernel:ir.call": self._h_ir_call, "kernel:ir.register": self._h_ir_register,
            "kernel:exec_python": self._h_exec_python, "kernel:ctx.set": self._h_ctx_set, "kernel:ctx.get": self._h_ctx_get,
            "kernel:ctx.copy": self._h_ctx_copy, "kernel:execute_flow": self._h_execute_flow,
            "kernel:save_flow": self._h_save_flow, "kernel:load_flows": self._h_load_flows,
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
        if path:
            return self._load_single_flow(Path(path))
        flow_dir = Path("flow")
        if not flow_dir.exists():
            self._flow = self._minimal_fallback_flow()
            return self._flow
        yaml_files = sorted(flow_dir.glob("*.flow.yaml"))
        if not yaml_files:
            self._flow = self._minimal_fallback_flow()
            return self._flow
        merged = {"flow_version": "2.0", "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
                  "pipelines": {"startup": [], "message": [], "message_stream": []}}
        for yaml_file in yaml_files:
            try:
                single = self._load_single_flow(yaml_file)
                if "defaults" in single:
                    merged["defaults"].update(single["defaults"])
                for pipeline_name, steps in single.get("pipelines", {}).items():
                    merged["pipelines"].setdefault(pipeline_name, [])
                    if isinstance(steps, list):
                        merged["pipelines"][pipeline_name].extend(steps)
                self.diagnostics.record_step(phase="startup", step_id=f"flow.load.{yaml_file.name}",
                                              handler="kernel:flow.load", status="success", meta={"file": str(yaml_file)})
            except Exception as e:
                self.diagnostics.record_step(phase="startup", step_id=f"flow.load.{yaml_file.name}",
                                              handler="kernel:flow.load", status="failed", error=e, meta={"file": str(yaml_file)})
        self._flow = merged
        return self._flow

    def _load_single_flow(self, flow_path: Path) -> Dict[str, Any]:
        if not flow_path.exists():
            raise FileNotFoundError(f"Flow file not found: {flow_path}")
        raw = flow_path.read_text(encoding="utf-8")
        parsed, _, _ = self._parse_flow_text(raw)
        return parsed

    def _minimal_fallback_flow(self) -> Dict[str, Any]:
        return {"flow_version": "2.0", "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
                "pipelines": {"startup": [{"id": "fallback.mounts", "run": {"handler": "kernel:mounts.init", "args": {"mounts_file": "user_data/mounts.json"}}},
                                          {"id": "fallback.registry", "run": {"handler": "kernel:registry.load", "args": {"ecosystem_dir": "ecosystem"}}},
                                          {"id": "fallback.active", "run": {"handler": "kernel:active_ecosystem.load", "args": {"config_file": "user_data/active_ecosystem.json"}}}],
                              "message": [], "message_stream": []}}

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

    def run_message(self, chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        flow = self._flow or self.load_flow()
        defaults = flow.get("defaults", {}) if isinstance(flow, dict) else {}
        fail_soft_default = bool(defaults.get("fail_soft", True))
        pipelines = flow.get("pipelines", {})
        message_steps = pipelines.get("message", []) if isinstance(pipelines, dict) else []
        message_steps = message_steps if isinstance(message_steps, list) else []
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {"fail_soft": fail_soft_default, "on_missing_handler": str(defaults.get("on_missing_handler", "skip")).lower()}
        ctx["chat_id"] = chat_id
        ctx["payload"] = payload or {}
        self.diagnostics.record_step(phase="message", step_id="message.pipeline.start", handler="kernel:message.run",
                                      status="success", meta={"step_count": len(message_steps), "chat_id": chat_id})
        aborted = False
        for step in message_steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="message", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(phase="message", step_id="message.pipeline.internal_error",
                                              handler="kernel:message.run", status="failed", error=e)
                if not fail_soft_default:
                    break
        self.diagnostics.record_step(phase="message", step_id="message.pipeline.end", handler="kernel:message.run",
                                      status="success" if not aborted else "failed", meta={"aborted": aborted, "chat_id": chat_id})
        out = ctx.get("output") or ctx.get("message_result")
        return out if isinstance(out, dict) else ({"result": out} if out is not None else {"success": False, "error": "No output produced"})

    def run_message_stream(self, chat_id: str, payload: Dict[str, Any]) -> Any:
        flow = self._flow or self.load_flow()
        defaults = flow.get("defaults", {}) if isinstance(flow, dict) else {}
        fail_soft_default = bool(defaults.get("fail_soft", True))
        pipelines = flow.get("pipelines", {})
        steps = pipelines.get("message_stream") if isinstance(pipelines, dict) else None
        steps = steps if isinstance(steps, list) else (pipelines.get("message", []) if isinstance(pipelines, dict) else [])
        steps = steps if isinstance(steps, list) else []
        payload2 = dict(payload or {})
        payload2["streaming"] = True
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {"fail_soft": fail_soft_default, "on_missing_handler": str(defaults.get("on_missing_handler", "skip")).lower()}
        ctx["chat_id"] = chat_id
        ctx["payload"] = payload2
        self.diagnostics.record_step(phase="message", step_id="message_stream.pipeline.start", handler="kernel:message_stream.run",
                                      status="success", meta={"step_count": len(steps), "chat_id": chat_id})
        aborted = False
        for step in steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="message", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(phase="message", step_id="message_stream.pipeline.internal_error",
                                              handler="kernel:message_stream.run", status="failed", error=e)
                if not fail_soft_default:
                    break
        self.diagnostics.record_step(phase="message", step_id="message_stream.pipeline.end", handler="kernel:message_stream.run",
                                      status="success" if not aborted else "failed", meta={"aborted": aborted, "chat_id": chat_id})
        return ctx.get("output") or ctx.get("message_result")

    # ========================================
    # Flow実行（IR登録形式）
    # ========================================

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

    # ハンドラ実装
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
