"""
kernel_handlers_system.py - 起動/システム系ハンドラ Mixin

Kernelの _h_* メソッドのうち起動・初期化・システム系を提供する。
Mixin方式でKernelクラスに合成される。

含まれるハンドラ:
- mounts/registry/active_ecosystem/interfaces
- security/approval/docker/container/privilege/api
- component discover/load
- ctx.set/get/copy, ir.get/call/register
- exec_python, execute_flow, save_flow, load_flows
- flow.compose
- emit, startup.failed, vocab.load, noop
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from .logging_utils import get_structured_logger
from .metrics import get_metrics_collector

_logger = get_structured_logger("rumi.kernel.handlers.system")

# ------------------------------------------------------------------
# Wave 17-A: inject ブロックリスト — 内部サービス参照の注入を禁止
# ------------------------------------------------------------------
_INJECT_BLOCKED_KEYS = frozenset({
    "interface_registry",
    "event_bus",
    "diagnostics",
    "install_journal",
    "permission_manager",
    "approval_manager",
    "lifecycle",
    "active_ecosystem",
    "registry",
})




class KernelSystemHandlersMixin:
    """
    起動/システム系ハンドラ Mixin

    __init__ を持たない。self の属性（diagnostics, interface_registry 等）は
    KernelCore.__init__ で初期化済みの前提でアクセスする。
    """

    # ------------------------------------------------------------------
    # ハンドラ登録（Kernel._init_kernel_handlers から呼ばれる）
    # ------------------------------------------------------------------

    def _register_system_handlers(self) -> Dict[str, Any]:
        """システム系ハンドラの辞書を返す"""
        return {
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
            "kernel:noop": self._h_noop,
        }

    # ------------------------------------------------------------------
    # mounts / registry / active_ecosystem / interfaces
    # ------------------------------------------------------------------

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
            _logger.error("Mounts init failed", exc_info=e, mounts_file=mounts_file)
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
            _logger.error("Registry load failed", exc_info=e, ecosystem_dir=ecosystem_dir)
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
            _logger.error("Active ecosystem load failed", exc_info=e, config_file=config_file)
            return None

    def _h_interfaces_publish(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        self.interface_registry.register("kernel.state", {"services_ready": True, "ts": self._now_ts()}, meta={"source": "kernel"})
        return {"services_ready": True}

    # ------------------------------------------------------------------
    # IR (Interface Registry) ハンドラ
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # ctx ハンドラ
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # exec_python / execute_flow / save_flow / load_flows
    # ------------------------------------------------------------------

    def _h_exec_python(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        file_arg = args.get("file")
        if not file_arg:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "missing 'file' argument"}}
        base_path = args.get("base_path") or ctx.get("_foreach_current_path", ".")
        full_path = Path(base_path) / file_arg if base_path and base_path != "." else Path(file_arg)

        # Wave 17-A: パストラバーサル防止
        full_path = full_path.resolve()
        try:
            full_path.relative_to(Path(base_path).resolve() if base_path and base_path != "." else Path(".").resolve())
        except ValueError:
            _logger.warning("Path traversal detected: %s (base: %s)", file_arg, base_path)
            return {"error": "Path traversal detected", "status": "blocked"}
        if not full_path.exists():
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "file_not_found", "path": str(full_path)}}
        phase = args.get("phase", "exec")
        exec_ctx = {"phase": phase, "ts": self._now_ts(), "paths": {"file": str(full_path), "dir": str(full_path.parent), "component_runtime_dir": str(full_path.parent)},
                    "ids": ctx.get("_foreach_ids", {}), "interface_registry": self.interface_registry, "event_bus": self.event_bus,
                    "diagnostics": self.diagnostics, "install_journal": self.install_journal}
        # Wave 17-A: inject ブロックリストで内部サービス参照の注入を制限
        for k, v in args.get("inject", {}).items():
            if k in _INJECT_BLOCKED_KEYS:
                _logger.warning("inject blocked for protected key: %s", k)
                continue
            exec_ctx[k] = self._resolve_value(v, ctx)
        try:
            self.lifecycle._exec_python_file(full_path, exec_ctx)
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"file": str(full_path), "phase": phase}}
        except Exception as e:
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": str(e), "file": str(full_path), "phase": phase}}

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

    # ------------------------------------------------------------------
    # flow.compose
    # ------------------------------------------------------------------

    def _h_flow_compose(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        try:
            from .flow_composer import get_flow_composer
            from .function_alias import get_function_alias_registry

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

    # ------------------------------------------------------------------
    # security / docker / approval / container / privilege / api
    # ------------------------------------------------------------------

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
            _logger.info("Security initialized", strict_mode=ctx["_strict_mode"])
            return {"_kernel_step_status": "success"}
        except Exception as e:
            _logger.error("Security init failed", exc_info=e, error=str(e))
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

        try:
            get_metrics_collector().set_gauge("docker.available", 1.0 if available else 0.0)
        except Exception:
            pass

        if required and not available:
            self.diagnostics.record_step(
                phase="startup",
                step_id="docker.check",
                handler="kernel:docker.check",
                status="failed",
                error={"type": "DockerNotAvailable", "message": "Docker is required but not available"},
                meta={"required": required}
            )
            _logger.error("Docker check failed: Docker is required but not available",
                          required=required)
            return {"_kernel_step_status": "failed", "_kernel_step_meta": {"error": "Docker not available"}}

        self.diagnostics.record_step(
            phase="startup",
            step_id="docker.check",
            handler="kernel:docker.check",
            status="success",
            meta={"available": available, "required": required}
        )
        _logger.info("Docker check completed", available=available, required=required)
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
            _logger.info("Approval manager initialized")
            return {"_kernel_step_status": "success"}
        except Exception as e:
            self.diagnostics.record_step(
                phase="startup",
                step_id="approval.init",
                handler="kernel:approval.init",
                status="failed",
                error=e
            )
            _logger.error("Approval manager init failed", exc_info=e, error=str(e))
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
            _logger.error("Container orchestrator init failed", exc_info=e, error=str(e))
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
            _logger.error("Host privilege manager init failed", exc_info=e, error=str(e))
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
                host_privilege_manager=ctx.get("host_privilege_manager"),
                kernel=self
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
            _logger.error("Pack API server init failed", exc_info=e, error=str(e))
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

        try:
            mc = get_metrics_collector()
            mc.increment("container.start.success", value=len(started))
            mc.increment("container.start.failure", value=len(failed))
        except Exception:
            pass

        self.diagnostics.record_step(
            phase="startup",
            step_id="container.start_approved",
            handler="kernel:container.start_approved",
            status="success",
            meta={"started": len(started), "failed_count": len(failed), "failed": failed}
        )
        _logger.info("Container start completed",
                      started_count=len(started), failed_count=len(failed))
        if failed:
            _logger.warning("Some containers failed to start",
                            failed_packs=[f["pack_id"] for f in failed])
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"started": started, "failed": failed}}

    # ------------------------------------------------------------------
    # component discover / load
    # ------------------------------------------------------------------

    def _h_component_discover(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        approved_only = args.get("approved_only", True)
        approved = ctx.get("_packs_approved", [])

        try:
            from backend_core.ecosystem.registry import get_registry
            reg = get_registry()


            # ActiveEcosystem の overrides/disabled を反映
            _active_eco = ctx.get("active_ecosystem")
            _overrides = {}
            _disabled_set = set()
            if _active_eco:
                try:
                    _overrides = _active_eco.get_all_overrides() if hasattr(_active_eco, 'get_all_overrides') else {}
                    _cfg = _active_eco.config
                    _disabled_set = set(getattr(_cfg, 'disabled_components', []))
                except Exception:
                    pass
            _override_selected = {}
            for _ct, _ci in _overrides.items():
                _override_selected[_ct] = _ci

            components = []
            for comp in reg.get_all_components():
                pack_id = getattr(comp, "pack_id", None)
                if approved_only and pack_id not in approved:
                    continue
                _full_id = getattr(comp, "full_id", None)
                _comp_type = getattr(comp, "type", None)
                _comp_id = getattr(comp, "id", None)

                # disabled チェック
                if _full_id and _full_id in _disabled_set:
                    continue
                # override チェック
                if _comp_type in _override_selected:
                    if _comp_id != _override_selected[_comp_type]:
                        continue

                components.append({
                    "full_id": _full_id,
                    "pack_id": pack_id,
                    "type": _comp_type,
                    "id": _comp_id
                })

            ctx["_discovered_components"] = components

            try:
                get_metrics_collector().set_gauge("component.discovered.count", float(len(components)))
            except Exception:
                pass

            self.diagnostics.record_step(
                phase="startup",
                step_id="component.discover",
                handler="kernel:component.discover",
                status="success",
                meta={"count": len(components), "approved_only": approved_only}
            )
            _logger.info("Component discovery completed",
                          count=len(components), approved_only=approved_only)
            return {"_kernel_step_status": "success", "_kernel_step_meta": {"count": len(components)}}
        except Exception as e:
            _logger.error("Component discovery failed", exc_info=e, error=str(e))
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

    # ------------------------------------------------------------------
    # emit / startup.failed / vocab.load / noop
    # ------------------------------------------------------------------

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

    def _h_noop(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """何もしないハンドラ(プレースホルダー)"""
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"handler": "noop"}}
