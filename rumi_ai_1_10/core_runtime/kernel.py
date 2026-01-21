"""
kernel.py - Flow Runner(用途非依存カーネル)

Flow駆動の用途非依存カーネル。
公式はドメイン知識を持たない。
"""

from __future__ import annotations

import json
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
        """Kernel内蔵 handler（ドメイン非依存プリミティブのみ）"""
        self._kernel_handlers = {
            # === 基盤初期化 ===
            "kernel:mounts.init": self._h_mounts_init,
            "kernel:registry.load": self._h_registry_load,
            "kernel:active_ecosystem.load": self._h_active_ecosystem_load,
            "kernel:interfaces.publish": self._h_interfaces_publish,
            
            # === 汎用プリミティブ ===
            "kernel:ir.get": self._h_ir_get,
            "kernel:ir.call": self._h_ir_call,
            "kernel:ir.register": self._h_ir_register,
            "kernel:exec_python": self._h_exec_python,
            "kernel:ctx.set": self._h_ctx_set,
            "kernel:ctx.get": self._h_ctx_get,
            "kernel:ctx.copy": self._h_ctx_copy,
        }

    def _resolve_handler(
        self,
        handler: str,
        args: Dict[str, Any] = None
    ) -> Optional[Callable[[Dict[str, Any], Dict[str, Any]], Any]]:
        """
        handler文字列を実行可能callableに解決する
        
        Args:
            handler: ハンドラ文字列（"kernel:xxx" または "component_phase:xxx"）
            args: Flow stepのargs（component_phaseに渡す）
        
        Returns:
            callable(args, ctx) -> Any
        """
        if not isinstance(handler, str) or not handler:
            return None
        
        if handler.startswith("kernel:"):
            return self._kernel_handlers.get(handler)
        
        if handler.startswith("component_phase:"):
            phase_name = handler.split(":", 1)[1].strip()
            # argsをクロージャにキャプチャ（filenameなどを渡す）
            captured_args = dict(args or {})
            
            def _call(call_args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
                # call_args（実行時）とcaptured_args（定義時）をマージ
                merged = {**captured_args, **call_args}
                return self.lifecycle.run_phase(phase_name, **merged)
            
            return _call
        
        return None

    def load_flow(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Flow(SSOT)を読み込む
        
        path指定時: そのファイルのみ読み込み
        path未指定時: flow/*.flow.yaml を全て読み込んでマージ
        """
        if path:
            # 単一ファイル指定時は従来通り
            return self._load_single_flow(Path(path))
        
        # flow/ ディレクトリから全て読み込み
        flow_dir = Path("flow")
        
        if not flow_dir.exists():
            # flowディレクトリが無ければfallback
            self._flow = self._minimal_fallback_flow()
            return self._flow
        
        # *.flow.yaml を優先度順に読み込み
        yaml_files = sorted(flow_dir.glob("*.flow.yaml"))
        
        if not yaml_files:
            # ファイルが無ければfallback
            self._flow = self._minimal_fallback_flow()
            return self._flow
        
        # マージ
        merged = {
            "flow_version": "2.0",
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {"startup": [], "message": [], "message_stream": []}
        }
        
        for yaml_file in yaml_files:
            try:
                single = self._load_single_flow(yaml_file)
                
                # defaults マージ
                if "defaults" in single:
                    merged["defaults"].update(single["defaults"])
                
                # pipelines マージ（追加）
                for pipeline_name, steps in single.get("pipelines", {}).items():
                    if pipeline_name not in merged["pipelines"]:
                        merged["pipelines"][pipeline_name] = []
                    if isinstance(steps, list):
                        merged["pipelines"][pipeline_name].extend(steps)
                
                self.diagnostics.record_step(
                    phase="startup",
                    step_id=f"flow.load.{yaml_file.name}",
                    handler="kernel:flow.load",
                    status="success",
                    meta={"file": str(yaml_file)}
                )
            except Exception as e:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id=f"flow.load.{yaml_file.name}",
                    handler="kernel:flow.load",
                    status="failed",
                    error=e,
                    meta={"file": str(yaml_file)}
                )
        
        self._flow = merged
        return self._flow

    def _load_single_flow(self, flow_path: Path) -> Dict[str, Any]:
        """単一のFlowファイルを読み込む"""
        if not flow_path.exists():
            raise FileNotFoundError(f"Flow file not found: {flow_path}")
        
        raw = flow_path.read_text(encoding="utf-8")
        parsed, used_parser, parser_meta = self._parse_flow_text(raw)
        
        return parsed

    def _minimal_fallback_flow(self) -> Dict[str, Any]:
        """
        最小限のfallback flow（ドメイン知識なし）
        
        flow/*.flow.yaml が存在しない場合のみ使用
        """
        return {
            "flow_version": "2.0",
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {
                "startup": [
                    {"id": "fallback.mounts", "run": {"handler": "kernel:mounts.init", "args": {"mounts_file": "user_data/mounts.json"}}},
                    {"id": "fallback.registry", "run": {"handler": "kernel:registry.load", "args": {"ecosystem_dir": "ecosystem"}}},
                    {"id": "fallback.active", "run": {"handler": "kernel:active_ecosystem.load", "args": {"config_file": "user_data/active_ecosystem.json"}}},
                ],
                "message": [],
                "message_stream": []
            }
        }

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
        out = ctx.get("output") or ctx.get("message_result")
        if out is not None:
            return out if isinstance(out, dict) else {"result": out}
        return {"success": False, "error": "No output produced", "meta": {"chat_id": chat_id}}

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
        
        return ctx.get("output") or ctx.get("message_result")
    
    # --- Helper methods ---
    
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
        
        # handler解決（argsも渡す）
        fn = self._resolve_handler(handler_str, args)
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
    
    # ========================================
    # 基盤初期化ハンドラ
    # ========================================
    
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
    
    def _h_interfaces_publish(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """services_ready"""
        self.interface_registry.register(
            "kernel.state",
            {"services_ready": True, "ts": self._now_ts()},
            meta={"source": "kernel"},
        )
        return {"services_ready": True}
    
    # ========================================
    # 汎用プリミティブハンドラ（ドメイン非依存）
    # ========================================

    def _h_ir_get(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        InterfaceRegistryから値を取得
        
        args:
            key: 取得するキー
            strategy: "first" | "last" | "all" (default: "last")
            store_as: 結果を格納するctxキー（オプション）
        """
        key = args.get("key")
        strategy = args.get("strategy", "last")
        store_as = args.get("store_as")
        
        if not key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'key' argument"}
            }
        
        value = self.interface_registry.get(key, strategy=strategy)
        
        if store_as:
            ctx[store_as] = value
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {
                "key": key,
                "strategy": strategy,
                "found": value is not None
            },
            "value": value
        }

    def _h_ir_call(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        InterfaceRegistryから取得して呼び出す
        
        args:
            key: 取得するキー
            strategy: "first" | "last" (default: "last")
            call_args: 呼び出し時の引数（オプション）
            store_as: 結果を格納するctxキー（オプション）
            pass_ctx: Trueならctx全体を渡す（オプション）
        """
        key = args.get("key")
        strategy = args.get("strategy", "last")
        call_args = args.get("call_args", {})
        store_as = args.get("store_as")
        pass_ctx = args.get("pass_ctx", False)
        
        if not key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'key' argument"}
            }
        
        fn = self.interface_registry.get(key, strategy=strategy)
        
        if fn is None:
            return {
                "_kernel_step_status": "skipped",
                "_kernel_step_meta": {"reason": "not_found", "key": key}
            }
        
        if not callable(fn):
            return {
                "_kernel_step_status": "skipped",
                "_kernel_step_meta": {"reason": "not_callable", "key": key}
            }
        
        # 変数展開
        resolved_args = self._resolve_args(call_args, ctx)
        
        # 呼び出し
        try:
            if pass_ctx:
                result = fn(ctx)
            elif resolved_args:
                result = fn(**resolved_args)
            else:
                result = fn()
        except TypeError:
            # 引数の型が合わない場合、ctx を渡してみる
            try:
                result = fn(ctx)
            except Exception as e:
                return {
                    "_kernel_step_status": "failed",
                    "_kernel_step_meta": {"error": f"call_failed: {type(e).__name__}: {e}", "key": key}
                }
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": f"{type(e).__name__}: {e}", "key": key}
            }
        
        if store_as:
            ctx[store_as] = result
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {"key": key, "has_result": result is not None},
            "result": result
        }

    def _h_ir_register(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        InterfaceRegistryに値を登録
        
        args:
            key: 登録するキー
            value: 直接指定する値（オプション）
            value_from_ctx: ctxから取得するキー（オプション）
            meta: メタデータ（オプション）
        """
        key = args.get("key")
        value = args.get("value")
        value_from_ctx = args.get("value_from_ctx")
        meta = args.get("meta", {})
        
        if not key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'key' argument"}
            }
        
        # 値の決定
        if value_from_ctx:
            actual_value = ctx.get(value_from_ctx)
        elif value is not None:
            actual_value = self._resolve_value(value, ctx)
        else:
            actual_value = None
        
        self.interface_registry.register(key, actual_value, meta=meta)
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {"key": key, "has_value": actual_value is not None}
        }

    def _h_exec_python(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Pythonファイルを実行（汎用・ドメイン非依存）
        
        args:
            file: 実行するファイル（相対パス可）
            base_path: 基準パス（オプション、foreachから設定される）
            phase: フェーズ名（オプション、ログ用）
            inject: 追加で注入する変数（オプション）
        """
        file_arg = args.get("file")
        base_path = args.get("base_path") or ctx.get("_foreach_current_path", ".")
        phase = args.get("phase", "exec")
        inject = args.get("inject", {})
        
        if not file_arg:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'file' argument"}
            }
        
        # パス解決
        if base_path and base_path != ".":
            full_path = Path(base_path) / file_arg
        else:
            full_path = Path(file_arg)
        
        if not full_path.exists():
            return {
                "_kernel_step_status": "skipped",
                "_kernel_step_meta": {"reason": "file_not_found", "path": str(full_path)}
            }
        
        # 実行コンテキスト構築
        exec_ctx = {
            "phase": phase,
            "ts": self._now_ts(),
            "paths": {
                "file": str(full_path),
                "dir": str(full_path.parent),
                "component_runtime_dir": str(full_path.parent),
            },
            "ids": ctx.get("_foreach_ids", {}),
            "interface_registry": self.interface_registry,
            "event_bus": self.event_bus,
            "diagnostics": self.diagnostics,
            "install_journal": self.install_journal,
        }
        
        # 追加注入
        for k, v in inject.items():
            exec_ctx[k] = self._resolve_value(v, ctx)
        
        # 実行
        try:
            self.lifecycle._exec_python_file(full_path, exec_ctx)
            return {
                "_kernel_step_status": "success",
                "_kernel_step_meta": {"file": str(full_path), "phase": phase}
            }
        except Exception as e:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {
                    "error": f"{type(e).__name__}: {e}",
                    "file": str(full_path),
                    "phase": phase
                }
            }

    def _h_ctx_set(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        コンテキストに値を設定
        
        args:
            key: 設定するキー
            value: 設定する値（${ctx.xxx} 形式の参照可）
        """
        key = args.get("key")
        value = args.get("value")
        
        if not key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'key' argument"}
            }
        
        ctx[key] = self._resolve_value(value, ctx)
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {"key": key}
        }

    def _h_ctx_get(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        コンテキストから値を取得
        
        args:
            key: 取得するキー
            default: デフォルト値（オプション）
            store_as: 別のキーに格納（オプション）
        """
        key = args.get("key")
        default = args.get("default")
        store_as = args.get("store_as")
        
        if not key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'key' argument"}
            }
        
        value = ctx.get(key, default)
        
        if store_as:
            ctx[store_as] = value
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {"key": key, "found": key in ctx},
            "value": value
        }

    def _h_ctx_copy(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        コンテキスト内で値をコピー
        
        args:
            from_key: コピー元キー
            to_key: コピー先キー
        """
        from_key = args.get("from_key")
        to_key = args.get("to_key")
        
        if not from_key or not to_key:
            return {
                "_kernel_step_status": "failed",
                "_kernel_step_meta": {"error": "missing 'from_key' or 'to_key' argument"}
            }
        
        ctx[to_key] = ctx.get(from_key)
        
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {"from_key": from_key, "to_key": to_key}
        }

    # ========================================
    # ヘルパーメソッド
    # ========================================

    def _resolve_args(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """引数内の変数参照を解決"""
        if not isinstance(args, dict):
            return {}
        
        resolved = {}
        for k, v in args.items():
            resolved[k] = self._resolve_value(v, ctx)
        return resolved

    def _resolve_value(self, value: Any, ctx: Dict[str, Any]) -> Any:
        """
        ${ctx.xxx} 形式の変数参照を解決
        
        サポート形式:
            ${ctx.key}          → ctx["key"]
            ${ctx.key.subkey}   → ctx["key"]["subkey"]（ネスト対応）
        """
        if not isinstance(value, str):
            return value
        
        if not value.startswith("${") or not value.endswith("}"):
            return value
        
        # ${ctx.xxx} の場合
        if value.startswith("${ctx."):
            path = value[6:-1]  # "ctx." の後から "}" の前まで
            parts = path.split(".")
            
            current = ctx
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None  # 見つからない場合
            return current
        
        # ${xxx} の場合（ctx直接参照）
        key = value[2:-1]
        return ctx.get(key)
