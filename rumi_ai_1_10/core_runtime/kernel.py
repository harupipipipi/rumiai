"""
kernel.py - Flow Runner(用途非依存カーネル)

Flow駆動の用途非依存カーネル。
"""

from __future__ import annotations

import json
import shutil
import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple, Callable

from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor


@dataclass
class KernelConfig:
    """Kernelの基本設定"""
    flow_path: str = "flow/project.flow.yaml"


class Kernel:
    """Flow駆動の用途非依存カーネル"""

    def __init__(
        self,
        config: Optional[KernelConfig] = None,
        diagnostics: Optional[Diagnostics] = None,
        install_journal: Optional[InstallJournal] = None,
        interface_registry: Optional[InterfaceRegistry] = None,
        event_bus: Optional[EventBus] = None,
        lifecycle: Optional[ComponentLifecycleExecutor] = None,
    ) -> None:
        self.config = config or KernelConfig()
        self.diagnostics = diagnostics or Diagnostics()
        self.install_journal = install_journal or InstallJournal()
        self.interface_registry = interface_registry or InterfaceRegistry()
        self.event_bus = event_bus or EventBus()
        self.lifecycle = lifecycle or ComponentLifecycleExecutor(
            diagnostics=self.diagnostics,
            install_journal=self.install_journal,
        )
        self._flow: Optional[Dict[str, Any]] = None
        self._kernel_handlers: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}
        self._init_kernel_handlers()

    def _now_ts(self) -> str:
        """ISO8601 (UTC)"""
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _init_kernel_handlers(self) -> None:
        """Kernel内蔵 handler を登録する"""
        self._kernel_handlers = {
            "kernel:mounts.init": self._h_mounts_init,
            "kernel:registry.load": self._h_registry_load,
            "kernel:active_ecosystem.load": self._h_active_ecosystem_load,
            "kernel:assets.seed": self._h_assets_seed,
            "kernel:interfaces.publish": self._h_interfaces_publish,
            "kernel:capability_graph.build": self._h_capability_graph_build,
            "kernel:context.assemble": self._h_context_assemble,
            "kernel:delegate.call": self._h_delegate_call,
            "kernel:persist": self._h_persist,
            "kernel:output": self._h_output,
        }

    def _resolve_handler(self, handler: str) -> Optional[Callable[[Dict[str, Any], Dict[str, Any]], Any]]:
        """handler文字列を実行可能callableに解決する"""
        if not isinstance(handler, str) or not handler:
            return None
        if handler.startswith("kernel:"):
            return self._kernel_handlers.get(handler)
        if handler.startswith("component_phase:"):
            phase_name = handler.split(":", 1)[1].strip()
            def _call(args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
                return self.lifecycle.run_phase(phase_name)
            return _call
        return None

    def load_flow(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Flow(SSOT)を読み込む - fail-soft + fallback(A) + Flow自動生成(B)"""
        flow_path = Path(path or self.config.flow_path)
        
        # Flowが無い場合は生成(B)：上書きしない
        generated = False
        generated_from: Optional[str] = None
        if not flow_path.exists():
            try:
                flow_path.parent.mkdir(parents=True, exist_ok=True)
                flow_path.write_text(self._fallback_flow_a_yaml_text(), encoding="utf-8")
                generated = True
                generated_from = "fallback_A"
            except Exception as e:
                self.diagnostics.record({
                    "ts": self._now_ts(),
                    "phase": "startup",
                    "step_id": "system.flow_autogenerate",
                    "handler": "kernel:flow.autogenerate",
                    "status": "failed",
                    "target": {"kind": "none", "id": None},
                    "error": {"type": type(e).__name__, "message": str(e)},
                    "meta": {"path": str(flow_path)},
                })
        
        # Flow読み込み(壊れてたら fallback(A))
        try:
            raw = flow_path.read_text(encoding="utf-8")
            parsed, used_parser, parser_meta = self._parse_flow_text(raw)
            
            # 最小検証
            pipelines = parsed.get("pipelines")
            if not isinstance(pipelines, dict):
                raise ValueError("Flow must contain 'pipelines' object")
            if "startup" not in pipelines or "message" not in pipelines:
                raise ValueError("Flow.pipelines must contain 'startup' and 'message'")
            if not isinstance(pipelines.get("startup"), list) or not isinstance(pipelines.get("message"), list):
                raise ValueError("Flow.pipelines.startup/message must be lists")
            if "message_stream" in pipelines and not isinstance(pipelines.get("message_stream"), list):
                raise ValueError("Flow.pipelines.message_stream must be a list if present")
            
            self._flow = parsed
            flow_origin = "generated_fallback" if generated else "user"
            
            self.diagnostics.record({
                "ts": self._now_ts(),
                "phase": "startup",
                "step_id": "system.flow_load",
                "handler": "kernel:flow.load",
                "status": "success",
                "target": {"kind": "none", "id": None},
                "error": None,
                "meta": {
                    "path": str(flow_path),
                    "generated": generated,
                    "generated_from": generated_from,
                    "flow_origin": flow_origin,
                    "used_parser": used_parser,
                    **parser_meta,
                },
            })
            
            return parsed
            
        except Exception as e:
            # 壊れたFlowは上書きしない。fail-softでfallback(A)に降りる
            fallback = self._fallback_flow_a()
            self._flow = fallback
            
            self.diagnostics.record({
                "ts": self._now_ts(),
                "phase": "startup",
                "step_id": "system.flow_load",
                "handler": "kernel:flow.load",
                "status": "failed",
                "target": {"kind": "none", "id": None},
                "error": {"type": type(e).__name__, "message": str(e)},
                "meta": {
                    "path": str(flow_path),
                    "fallback": "A",
                    "generated": generated,
                    "generated_from": generated_from,
                    "flow_origin": "generated_fallback" if generated else "user",
                },
            })
            
            return fallback

    def run_startup(self) -> Dict[str, Any]:
        """Startup Pipelineを実行する(Flow準拠)"""
        flow = self._flow or self.load_flow()
        
        defaults = flow.get("defaults") if isinstance(flow, dict) else {}
        if not isinstance(defaults, dict):
            defaults = {}
        
        fail_soft_default = bool(defaults.get("fail_soft", True))
        on_missing_handler = str(defaults.get("on_missing_handler", "skip")).strip().lower()
        
        pipelines = flow.get("pipelines", {})
        startup_steps = []
        if isinstance(pipelines, dict):
            startup_steps = pipelines.get("startup", []) or []
        if not isinstance(startup_steps, list):
            startup_steps = []
        
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {
            "fail_soft": fail_soft_default,
            "on_missing_handler": on_missing_handler,
        }
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="startup.pipeline.start",
            handler="kernel:startup.run",
            status="success",
            meta={"step_count": len(startup_steps)},
        )
        
        aborted = False
        for step in startup_steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="startup", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="startup.pipeline.internal_error",
                    handler="kernel:startup.run",
                    status="failed",
                    error=e,
                    meta={"note": "Kernel internal error during step execution"},
                )
                if not fail_soft_default:
                    break
        
        self.diagnostics.record_step(
            phase="startup",
            step_id="startup.pipeline.end",
            handler="kernel:startup.run",
            status="success" if not aborted else "failed",
            meta={"aborted": aborted},
        )
        
        return self.diagnostics.as_dict()

    def run_message(self, chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Message Pipelineを実行する(Flow準拠)"""
        flow = self._flow or self.load_flow()
        
        defaults = flow.get("defaults") if isinstance(flow, dict) else {}
        if not isinstance(defaults, dict):
            defaults = {}
        
        fail_soft_default = bool(defaults.get("fail_soft", True))
        on_missing_handler = str(defaults.get("on_missing_handler", "skip")).strip().lower()
        
        pipelines = flow.get("pipelines", {})
        message_steps = []
        if isinstance(pipelines, dict):
            message_steps = pipelines.get("message", []) or []
        if not isinstance(message_steps, list):
            message_steps = []
        
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {
            "fail_soft": fail_soft_default,
            "on_missing_handler": on_missing_handler,
        }
        ctx["chat_id"] = chat_id
        ctx["payload"] = payload or {}
        ctx["message_state"] = {
            "result": None,
            "output": None,
        }
        
        self.diagnostics.record_step(
            phase="message",
            step_id="message.pipeline.start",
            handler="kernel:message.run",
            status="success",
            meta={"step_count": len(message_steps), "chat_id": chat_id},
        )
        
        aborted = False
        for step in message_steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="message", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(
                    phase="message",
                    step_id="message.pipeline.internal_error",
                    handler="kernel:message.run",
                    status="failed",
                    error=e,
                    meta={"note": "Kernel internal error during message step execution", "chat_id": chat_id},
                )
                if not fail_soft_default:
                    break
        
        self.diagnostics.record_step(
            phase="message",
            step_id="message.pipeline.end",
            handler="kernel:message.run",
            status="success" if not aborted else "failed",
            meta={"aborted": aborted, "chat_id": chat_id},
        )
        
        # 出力決定(fail-soft)
        state = ctx.get("message_state", {}) if isinstance(ctx.get("message_state"), dict) else {}
        out = state.get("output") or state.get("result")
        if isinstance(out, dict):
            return out
        # 最低限のフォールバック
        return {"success": False, "error": "No message output produced", "chat_id": chat_id}

    def run_message_stream(self, chat_id: str, payload: Dict[str, Any]) -> Any:
        """Message Stream Pipelineを実行する(Flow準拠)"""
        flow = self._flow or self.load_flow()
        
        defaults = flow.get("defaults") if isinstance(flow, dict) else {}
        if not isinstance(defaults, dict):
            defaults = {}
        
        fail_soft_default = bool(defaults.get("fail_soft", True))
        on_missing_handler = str(defaults.get("on_missing_handler", "skip")).strip().lower()
        
        pipelines = flow.get("pipelines", {})
        steps = []
        if isinstance(pipelines, dict):
            stream_steps = pipelines.get("message_stream")
            if isinstance(stream_steps, list):
                steps = stream_steps
            else:
                # フォールバック：message を使う
                steps = pipelines.get("message", []) or []
        if not isinstance(steps, list):
            steps = []
        
        # streaming フラグは必ず true にする
        payload2 = dict(payload or {})
        payload2["streaming"] = True
        
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {
            "fail_soft": fail_soft_default,
            "on_missing_handler": on_missing_handler,
        }
        ctx["chat_id"] = chat_id
        ctx["payload"] = payload2
        ctx["message_state"] = {"result": None, "output": None}
        
        self.diagnostics.record_step(
            phase="message",
            step_id="message_stream.pipeline.start",
            handler="kernel:message_stream.run",
            status="success",
            meta={"step_count": len(steps), "chat_id": chat_id},
        )
        
        aborted = False
        for step in steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase="message", ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(
                    phase="message",
                    step_id="message_stream.pipeline.internal_error",
                    handler="kernel:message_stream.run",
                    status="failed",
                    error=e,
                    meta={"note": "Kernel internal error during message_stream step execution", "chat_id": chat_id},
                )
                if not fail_soft_default:
                    break
        
        self.diagnostics.record_step(
            phase="message",
            step_id="message_stream.pipeline.end",
            handler="kernel:message_stream.run",
            status="success" if not aborted else "failed",
            meta={"aborted": aborted, "chat_id": chat_id},
        )
        
        state = ctx.get("message_state", {}) if isinstance(ctx.get("message_state"), dict) else {}
        return state.get("output") or state.get("result")
    
    # --- Helper methods ---
    
    def _fallback_flow_a(self) -> Dict[str, Any]:
        """fallback flow (A): minimal working flow"""
        return {
            "flow_version": "1.0",
            "project": {"id": "rumi_ai", "title": "Rumi AI OS (fallback)"},
            "defaults": {
                "fail_soft": True,
                "on_missing_handler": "skip",
                "diagnostics": {"enabled": True},
                "install_journal": {
                    "enabled": True,
                    "dir": "user_data/settings/ecosystem/install_journal",
                },
            },
            "pipelines": {
                "startup": [
                    {"id": "startup.mounts", "run": {"handler": "kernel:mounts.init", "args": {"mounts_file": "user_data/mounts.json"}}},
                    {"id": "startup.registry", "run": {"handler": "kernel:registry.load", "args": {"ecosystem_dir": "ecosystem"}}},
                    {"id": "startup.active_ecosystem", "run": {"handler": "kernel:active_ecosystem.load", "args": {"config_file": "user_data/active_ecosystem.json"}}},
                    {"id": "startup.dependency", "run": {"handler": "component_phase:dependency", "args": {}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "startup.setup", "run": {"handler": "component_phase:setup", "args": {}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "startup.services_ready", "run": {"handler": "kernel:interfaces.publish", "args": {}}, "optional": True, "on_error": {"action": "continue"}},
                ],
                "message": [
                    {"id": "message.context_assemble", "run": {"handler": "kernel:context.assemble", "args": {}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message.invoke_reference", "run": {"handler": "kernel:delegate.call", "args": {"interface_key": "reference.message_handler"}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message.persist", "run": {"handler": "kernel:persist", "args": {"targets": ["history", "ui_history", "chat_config"]}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message.output", "run": {"handler": "kernel:output", "args": {"mode": "auto"}}, "optional": True, "on_error": {"action": "continue"}},
                ],
                "message_stream": [
                    {"id": "message_stream.context_assemble", "run": {"handler": "kernel:context.assemble", "args": {}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message_stream.invoke_reference", "run": {"handler": "kernel:delegate.call", "args": {"interface_key": "reference.message_handler_stream"}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message_stream.persist", "run": {"handler": "kernel:persist", "args": {"targets": ["history", "ui_history", "chat_config"]}}, "optional": True, "on_error": {"action": "continue"}},
                    {"id": "message_stream.output", "run": {"handler": "kernel:output", "args": {"mode": "auto"}}, "optional": True, "on_error": {"action": "continue"}},
                ],
            },
        }
    
    def _fallback_flow_a_yaml_text(self) -> str:
        """fallback flow(A)をYAMLテキストとして返す"""
        return '''flow_version: "1.0"
project:
  id: "rumi_ai"
  title: "Rumi AI OS (fallback)"
defaults:
  fail_soft: true
  on_missing_handler: "skip"
  diagnostics:
    enabled: true
  install_journal:
    enabled: true
    dir: "user_data/settings/ecosystem/install_journal"
pipelines:
  startup:
    - id: "startup.mounts"
      run:
        handler: "kernel:mounts.init"
        args:
          mounts_file: "user_data/mounts.json"
    - id: "startup.registry"
      run:
        handler: "kernel:registry.load"
        args:
          ecosystem_dir: "ecosystem"
    - id: "startup.active_ecosystem"
      run:
        handler: "kernel:active_ecosystem.load"
        args:
          config_file: "user_data/active_ecosystem.json"
    - id: "startup.dependency"
      run:
        handler: "component_phase:dependency"
        args: {}
      optional: true
      on_error:
        action: "continue"
    - id: "startup.setup"
      run:
        handler: "component_phase:setup"
        args: {}
      optional: true
      on_error:
        action: "continue"
    - id: "startup.services_ready"
      run:
        handler: "kernel:interfaces.publish"
        args: {}
      optional: true
      on_error:
        action: "continue"
  message: []
  message_stream: []
'''
    
    def _parse_flow_text(self, raw: str) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """Flowテキストをdictにパースする"""
        attempts: List[Dict[str, Any]] = []
        
        # 1) PyYAMLがあれば最優先で使う
        try:
            import yaml  # type: ignore
            try:
                parsed_any = yaml.safe_load(raw)
                if isinstance(parsed_any, dict):
                    return parsed_any, "yaml_pyyaml", {"parser_attempts": attempts}
                attempts.append({
                    "name": "yaml_pyyaml",
                    "status": "failed",
                    "reason": f"returned {type(parsed_any).__name__}, expected dict",
                })
            except Exception as e:
                attempts.append({
                    "name": "yaml_pyyaml",
                    "status": "failed",
                    "reason": f"{type(e).__name__}: {e}",
                })
        except Exception as e:
            attempts.append({
                "name": "yaml_pyyaml",
                "status": "unavailable",
                "reason": f"{type(e).__name__}: {e}",
            })
        
        # 2) JSON(JSON互換YAMLや、生成したFlowを読むための最後の手段)
        try:
            parsed_any = json.loads(raw)
            if isinstance(parsed_any, dict):
                return parsed_any, "json", {"parser_attempts": attempts}
            attempts.append({
                "name": "json",
                "status": "failed",
                "reason": f"returned {type(parsed_any).__name__}, expected dict",
            })
        except Exception as e:
            attempts.append({
                "name": "json",
                "status": "failed",
                "reason": f"{type(e).__name__}: {e}",
            })
        
        raise ValueError("Unable to parse Flow as YAML or JSON")
    
    def _build_kernel_context(self) -> Dict[str, Any]:
        """Kernel/Componentが共有して参照できるコンテキスト"""
        ctx: Dict[str, Any] = {
            "diagnostics": self.diagnostics,
            "install_journal": self.install_journal,
            "interface_registry": self.interface_registry,
            "event_bus": self.event_bus,
            "lifecycle": self.lifecycle,
            "mount_manager": None,
            "registry": None,
            "active_ecosystem": None,
        }
        
        # 可能なら backend_core のグローバルを注入
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
        
        # lifecycleにも注入
        try:
            self.lifecycle.interface_registry = self.interface_registry
            self.lifecycle.event_bus = self.event_bus
        except Exception:
            pass
        
        ctx.setdefault("_disabled_targets", {"packs": set(), "components": set()})
        return ctx
    
    def _execute_flow_step(self, step: Any, phase: str, ctx: Dict[str, Any]) -> bool:
        """1ステップ実行。Returns: aborted"""
        step_id = None
        handler = None
        args: Dict[str, Any] = {}
        optional = False
        on_error_action = None
        
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
        
        # handler解決
        fn = self._resolve_handler(handler_str)
        if fn is None:
            missing_policy = str(ctx.get("_flow_defaults", {}).get("on_missing_handler", "skip")).lower()
            if missing_policy == "error" and not optional:
                self.diagnostics.record_step(
                    phase=phase,
                    step_id=step_id_str,
                    handler=handler_str,
                    status="failed",
                    error={"type": "MissingHandler", "message": f"handler not found: {handler_str}"},
                    meta={"optional": optional, "on_missing_handler": missing_policy},
                )
                return True  # abort
            
            self.diagnostics.record_step(
                phase=phase,
                step_id=step_id_str,
                handler=handler_str,
                status="skipped",
                meta={"reason": "missing_handler", "optional": optional, "on_missing_handler": missing_policy},
            )
            return False
        
        # 実行
        self.diagnostics.record_step(
            phase=phase,
            step_id=f"{step_id_str}.start",
            handler=handler_str,
            status="success",
            meta={"args": args},
        )
        
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
            
            self.diagnostics.record_step(
                phase=phase,
                step_id=f"{step_id_str}.done",
                handler=handler_str,
                status=done_status,
                meta=done_meta,
            )
            return False
        except Exception as e:
            action = str(on_error_action or ("continue" if ctx.get("_flow_defaults", {}).get("fail_soft", True) else "abort")).lower()
            
            status = "failed"
            if action == "disable_target":
                status = "disabled"
            self.diagnostics.record_step(
                phase=phase,
                step_id=f"{step_id_str}.failed",
                handler=handler_str,
                status=status,
                error=e,
                meta={"on_error.action": action, "optional": optional},
            )
            
            if action == "abort":
                return True
            return False
    
    # --- Built-in handlers (kernel:*) ---
    
    def _h_mounts_init(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """mounts初期化"""
        mounts_file = str(args.get("mounts_file", "user_data/mounts.json"))
        try:
            from backend_core.ecosystem.mounts import DEFAULT_MOUNTS, initialize_mounts, get_mount_manager
            
            mf = Path(mounts_file)
            if not mf.exists():
                mf.parent.mkdir(parents=True, exist_ok=True)
                mf.write_text(
                    json.dumps({"version": "1.0", "mounts": DEFAULT_MOUNTS}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            
            initialize_mounts(config_path=str(mf))
            mm = get_mount_manager()
            ctx["mount_manager"] = mm
            self.interface_registry.register("ecosystem.mount_manager", mm, meta={"source": "kernel"})
            return mm
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="startup.mounts.internal",
                handler="kernel:mounts.init",
                status="failed",
                error=e,
                meta={"mounts_file": mounts_file},
            )
            return None
    
    def _h_registry_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """registry初期化"""
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
            self.diagnostics.record_step(
                phase="startup",
                step_id="startup.registry.internal",
                handler="kernel:registry.load",
                status="failed",
                error=e,
                meta={"ecosystem_dir": ecosystem_dir},
            )
            return None
    
    def _h_active_ecosystem_load(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """active_ecosystem初期化"""
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
            self.diagnostics.record_step(
                phase="startup",
                step_id="startup.active_ecosystem.internal",
                handler="kernel:active_ecosystem.load",
                status="failed",
                error=e,
                meta={"config_file": config_file},
            )
            return None
    
    def _h_assets_seed(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """assets seed（簡易実装）"""
        return {
            "_kernel_step_status": "skipped",
            "_kernel_step_meta": {"reason": "not_implemented_yet", "args": args},
        }
    
    def _h_interfaces_publish(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """services_ready"""
        self.interface_registry.register(
            "kernel.state",
            {"services_ready": True, "ts": self._now_ts()},
            meta={"source": "kernel"},
        )
        return {"services_ready": True}
    
    def _h_capability_graph_build(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """capability_graph（器・用途非依存）"""
        graph = {
            "version": "0.1",
            "ts": self._now_ts(),
            "nodes": [],
            "edges": [],
            "meta": {"note": "capability graph placeholder"},
        }
        self.interface_registry.register("capability.graph", graph, meta={"source": "kernel"})
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"registered": "capability.graph"}}
    
    def _h_context_assemble(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """context_assemble: history/ui_history/chat_config を読み、ctxに載せる"""
        chat_id = ctx.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "missing_chat_id"}}
        
        try:
            from chat_manager import ChatManager
            cm = ChatManager()
            ctx["chat_manager"] = cm
        except Exception as e:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": f"chat_manager_unavailable:{type(e).__name__}:{e}"}}
        
        cm = ctx.get("chat_manager")
        try:
            ctx["history"] = cm.load_chat_history(chat_id)
        except Exception:
            ctx["history"] = None
        try:
            ctx["ui_history"] = cm.load_ui_history(chat_id)
        except Exception:
            ctx["ui_history"] = None
        try:
            ctx["chat_config"] = cm.load_chat_config(chat_id)
        except Exception:
            ctx["chat_config"] = None
        
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"loaded": ["history", "ui_history", "chat_config"]}}
    
    def _h_delegate_call(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """delegate.call: Interface Registry から callable を取り出して実行"""
        key = args.get("interface_key")
        if not isinstance(key, str) or not key:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "missing_interface_key"}}
        
        fn = self.interface_registry.get(key, strategy="last")
        if fn is None or not callable(fn):
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "callable_not_found", "interface_key": key}}
        
        chat_id = ctx.get("chat_id")
        payload = ctx.get("payload", {})
        try:
            result = fn(chat_id, payload)
        except TypeError:
            result = fn(ctx)
        
        # 結果を格納
        if isinstance(ctx.get("message_state"), dict):
            ctx["message_state"]["result"] = result
            
            # 重要：persistの競合回避
            is_streaming = False
            try:
                payload_check = ctx.get("payload", {})
                if isinstance(payload_check, dict) and bool(payload_check.get("streaming", False)):
                    is_streaming = True
            except Exception:
                pass
            
            try:
                from flask import Response as FlaskResponse  # type: ignore
                if isinstance(result, FlaskResponse):
                    is_streaming = True
            except Exception:
                pass
            
            if is_streaming:
                ctx["message_state"]["skip_persist"] = True
        
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"interface_key": key}}
    
    def _h_persist(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """persist: history/ui_history/chat_config を保存する"""
        cm = ctx.get("chat_manager")
        chat_id = ctx.get("chat_id")
        if cm is None or not isinstance(chat_id, str) or not chat_id:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "missing_chat_manager_or_chat_id"}}
        
        # delegateがストリーミング/Responseを返した場合、persistは破壊的になり得るためスキップ
        state = ctx.get("message_state", {})
        if isinstance(state, dict) and state.get("skip_persist") is True:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "skip_persist_for_streaming_or_response"}}
        
        targets = args.get("targets", ["history", "ui_history", "chat_config"])
        if not isinstance(targets, list):
            targets = ["history", "ui_history", "chat_config"]
        
        # 最新を再読込して保存
        saved = []
        try:
            latest_history = cm.load_chat_history(chat_id) if "history" in targets else None
        except Exception:
            latest_history = None
        try:
            latest_ui = cm.load_ui_history(chat_id) if "ui_history" in targets else None
        except Exception:
            latest_ui = None
        try:
            latest_cfg = cm.load_chat_config(chat_id) if "chat_config" in targets else None
        except Exception:
            latest_cfg = None
        
        if "history" in targets and isinstance(latest_history, dict):
            try:
                cm.save_chat_history(chat_id, latest_history)
                ctx["history"] = latest_history
                saved.append("history")
            except Exception:
                pass
        if "ui_history" in targets and isinstance(latest_ui, dict):
            try:
                cm.save_ui_history(chat_id, latest_ui)
                ctx["ui_history"] = latest_ui
                saved.append("ui_history")
            except Exception:
                pass
        if "chat_config" in targets and isinstance(latest_cfg, dict):
            try:
                cm.save_chat_config(chat_id, latest_cfg)
                ctx["chat_config"] = latest_cfg
                saved.append("chat_config")
            except Exception:
                pass
        
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"saved": saved}}
    
    def _h_output(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """output: message_state.result をそのまま output として確定する"""
        state = ctx.get("message_state", {})
        if not isinstance(state, dict):
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "missing_message_state"}}
        out = state.get("result")
        state["output"] = out
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"has_output": isinstance(out, dict)}}
