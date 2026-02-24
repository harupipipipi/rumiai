"""
component_lifecycle.py - Component Lifecycle Executor
スレッドセーフ、使用追跡、Hot Reload対応版
承認チェック機能付き、セキュアエグゼキューター統合
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict, List, Set
from contextlib import contextmanager
from threading import RLock

from .diagnostics import Diagnostics
from .install_journal import InstallJournal

logger = logging.getLogger(__name__)

# --- sys.path shadow protection (W17-C) ---
_DANGEROUS_MODULE_NAMES = frozenset({
    "os", "sys", "json", "logging", "subprocess", "importlib",
    "pathlib", "threading", "socket", "http", "hashlib", "hmac",
    "secrets", "ssl", "sqlite3", "shutil", "tempfile", "signal",
    "re", "io", "abc", "typing", "collections", "functools",
    "dataclasses", "enum", "copy", "pickle", "base64", "uuid",
    "contextlib", "inspect", "traceback", "struct", "array",
    "math", "random", "time", "datetime", "csv", "xml",
    "email", "html", "urllib", "asyncio", "multiprocessing",
    "ctypes", "configparser", "argparse", "getpass", "platform",
})


def _has_shadow_module(directory: Path) -> str | None:
    """Return the first dangerous module name found in *directory*, or None."""
    if not directory.is_dir():
        return None
    for item in directory.iterdir():
        name = item.stem if item.is_file() else item.name
        if name in _DANGEROUS_MODULE_NAMES:
            return name
    return None


@dataclass
class ComponentLifecycleExecutor:
    diagnostics: Diagnostics
    install_journal: InstallJournal
    registry: Optional[Any] = None
    active_ecosystem: Optional[Any] = None
    interface_registry: Optional[Any] = None
    event_bus: Optional[Any] = None
    _disabled_components_runtime: Set[str] = field(default_factory=set)
    _usage_counters: Dict[str, int] = field(default_factory=dict)
    _usage_lock: RLock = field(default_factory=RLock)

    # --- environment variable freezing keys (W17-C) ---
    _FROZEN_ENV_KEYS = ("RUMI_SECURITY_MODE",)

    @staticmethod
    def _snapshot_env() -> dict[str, str | None]:
        """Capture the current values of security-critical env vars."""
        return {k: os.environ.get(k) for k in ComponentLifecycleExecutor._FROZEN_ENV_KEYS}

    @staticmethod
    def _restore_env(snapshot: dict[str, str | None]) -> None:
        """Restore security-critical env vars from *snapshot*.

        If a value was tampered with, log a warning before restoring.
        """
        for key, original in snapshot.items():
            current = os.environ.get(key)
            if current != original:
                logger.warning(
                    "SECURITY: env var %s was modified during pack execution "
                    "(was %r, now %r). Restoring original value.",
                    key, original, current,
                )
                try:
                    from .audit_logger import get_audit_logger
                    get_audit_logger().log_security_event(
                        event_type="env_var_tamper_detected",
                        severity="critical",
                        description=f"Env var {key} tampered: {original!r} -> {current!r}",
                        details={"key": key, "original": original, "tampered": current},
                    )
                except Exception:
                    pass
                if original is not None:
                    os.environ[key] = original
                elif key in os.environ:
                    del os.environ[key]

    def _now_ts(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _get_registry(self) -> Any:
        if self.registry is not None:
            return self.registry
        from backend_core.ecosystem.registry import get_registry
        self.registry = get_registry()
        return self.registry

    def _get_active(self) -> Any:
        if self.active_ecosystem is not None:
            return self.active_ecosystem
        from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager
        self.active_ecosystem = get_active_ecosystem_manager()
        return self.active_ecosystem

    def begin_use(self, component_id: str) -> None:
        with self._usage_lock:
            self._usage_counters[component_id] = self._usage_counters.get(component_id, 0) + 1

    def end_use(self, component_id: str) -> None:
        with self._usage_lock:
            if component_id in self._usage_counters:
                self._usage_counters[component_id] = max(0, self._usage_counters[component_id] - 1)

    def get_usage(self, component_id: str) -> int:
        with self._usage_lock:
            return self._usage_counters.get(component_id, 0)

    def drain(self, component_id: str, timeout: float = 30.0) -> bool:
        import time
        start = time.time()
        while time.time() - start < timeout:
            with self._usage_lock:
                if self._usage_counters.get(component_id, 0) == 0:
                    return True
            time.sleep(0.1)
        return False

    def reload_component(self, component_full_id: str) -> Dict[str, Any]:
        if self.get_usage(component_full_id) > 0:
            return {"status": "failed", "error": f"Component {component_full_id} is in use"}
        if self.interface_registry:
            entries = self.interface_registry.find(lambda k, e: e.get("meta", {}).get("_source_component") == component_full_id)
            for entry in entries:
                self.interface_registry.unregister(entry["key"], lambda e, t=entry: e.get("ts") == t.get("ts"))
        to_remove = [n for n in sys.modules.keys() if component_full_id.replace(":", "_") in n]
        for name in to_remove:
            del sys.modules[name]
        reg = self._get_registry()
        component = None
        for pack in reg.packs.values():
            for comp in pack.components.values():
                if getattr(comp, "full_id", None) == component_full_id:
                    component = comp
                    break
        if component is None:
            return {"status": "failed", "error": f"Component {component_full_id} not found"}
        self._run_phase_for_component("setup", component)
        return {"status": "success", "component_id": component_full_id}

    def iter_active_components(self, phase: Optional[str] = None) -> List[Any]:
        reg = self._get_registry()
        active = self._get_active()
        pack = None
        try:
            pack = reg.get_pack_by_identity(active.active_pack_identity)
        except Exception:
            pass
        if pack is None and getattr(reg, "packs", None):
            pack = list(reg.packs.values())[0]
        if pack is None:
            return []
        comps: List[Any] = list(getattr(pack, "components", {}).values())
        if not comps:
            return []
        disabled_persistent: Set[str] = set()
        try:
            disabled_persistent = set(getattr(active.config, "disabled_components", []) or [])
        except Exception:
            pass
        phase_name = (phase or "").strip()
        comps_sorted = sorted(comps, key=lambda x: (getattr(x, "pack_id", ""), getattr(x, "type", ""), getattr(x, "id", ""), getattr(x, "version", "")))
        active_list: List[Any] = []
        for c in comps_sorted:
            full_id = getattr(c, "full_id", None)
            comp_full_id = full_id if isinstance(full_id, str) else f"{getattr(c,'pack_id',None)}:{getattr(c,'type',None)}:{getattr(c,'id',None)}"
            if comp_full_id in disabled_persistent or comp_full_id in self._disabled_components_runtime:
                self.diagnostics.record_step(phase="startup", step_id="component.filter", handler="component_lifecycle:filter",
                                              status="skipped", target={"kind": "component", "id": comp_full_id}, meta={"phase": phase_name})
                continue
            active_list.append(c)
        return active_list

    def run_phase(self, phase_name: str, **kwargs) -> Dict[str, Any]:
        phase = (phase_name or "").strip()
        if not phase:
            return {"_kernel_step_status": "skipped", "_kernel_step_meta": {"reason": "empty_phase_name"}}
        filename = kwargs.get("filename") or f"{phase}.py"
        components = self.iter_active_components(phase=phase)
        self._ensure_components_on_syspath(components)
        self.diagnostics.record_step(phase="startup", step_id=f"component_phase.{phase}.start", handler=f"component_phase:{phase}",
                                      status="success", meta={"count": len(components), "filename": filename})
        before_disabled = set(self._disabled_components_runtime)
        for comp in components:
            self._run_phase_for_component(phase, comp, filename=filename)
        newly_disabled = sorted(list(set(self._disabled_components_runtime) - before_disabled))
        self.diagnostics.record_step(phase="startup", step_id=f"component_phase.{phase}.end", handler=f"component_phase:{phase}",
                                      status="success", meta={"disabled_runtime_count": len(self._disabled_components_runtime)})
        return {"_kernel_step_status": "success", "_kernel_step_meta": {"phase": phase, "count": len(components), "newly_disabled": newly_disabled, "filename": filename},
                "_kernel_disable_targets": [{"kind": "component", "id": cid} for cid in newly_disabled]}

    def _ensure_components_on_syspath(self, components: list) -> None:
        try:
            for comp in components:
                p = str(Path(getattr(comp, "path", ".")).resolve())
                if p and p not in sys.path:
                    shadow = _has_shadow_module(Path(p))
                    if shadow is not None:
                        logger.critical(
                            "SECURITY: Pack component at %s contains module '%s' "
                            "which shadows a standard library module. "
                            "Skipping sys.path addition.",
                            p, shadow,
                        )
                        try:
                            from .audit_logger import get_audit_logger
                            get_audit_logger().log_security_event(
                                event_type="syspath_shadow_blocked",
                                severity="critical",
                                description=f"Module shadow attempt: {shadow}",
                                details={"path": p, "module": shadow},
                            )
                        except Exception:
                            pass
                    else:
                        sys.path.insert(0, p)
        except Exception:
            pass

    @contextmanager
    def _scoped_syspath(self, components: list):
        added: List[str] = []
        try:
            for comp in components:
                p = str(Path(getattr(comp, "path", ".")).resolve())
                if p and p not in sys.path:
                    shadow = _has_shadow_module(Path(p))
                    if shadow is not None:
                        logger.critical(
                            "SECURITY: Pack component at %s contains module '%s' "
                            "which shadows a standard library module. "
                            "Skipping sys.path addition.",
                            p, shadow,
                        )
                        try:
                            from .audit_logger import get_audit_logger
                            get_audit_logger().log_security_event(
                                event_type="syspath_shadow_blocked",
                                severity="critical",
                                description=f"Module shadow attempt: {shadow}",
                                details={"path": p, "module": shadow},
                            )
                        except Exception:
                            pass
                    else:
                        sys.path.insert(0, p)
                        added.append(p)
            yield
        finally:
            for p in reversed(added):
                try:
                    sys.path.remove(p)
                except ValueError:
                    pass

    def _run_phase_for_component(self, phase: str, component: Any, filename: str = None) -> None:
        full_id = getattr(component, "full_id", None)
        comp_id = full_id if isinstance(full_id, str) else f"{getattr(component,'pack_id',None)}:{getattr(component,'type',None)}:{getattr(component,'id',None)}"
        pack_id = getattr(component, "pack_id", None)
        
        try:
            from .approval_manager import get_approval_manager, PackStatus
            am = get_approval_manager()
            if am._initialized:
                status = am.get_status(pack_id)
                if status != PackStatus.APPROVED:
                    self.diagnostics.record_step(
                        phase=phase,
                        step_id=f"{phase}.{comp_id}.not_approved",
                        handler=f"component_phase:{phase}",
                        status="skipped",
                        target={"kind": "component", "id": comp_id},
                        meta={
                            "reason": "pack_not_approved",
                            "pack_id": pack_id,
                            "pack_status": status.value if status else "unknown"
                        }
                    )
                    return
                
                if not am.verify_hash(pack_id):
                    am.mark_modified(pack_id)
                    self.diagnostics.record_step(
                        phase=phase,
                        step_id=f"{phase}.{comp_id}.hash_mismatch",
                        handler=f"component_phase:{phase}",
                        status="skipped",
                        target={"kind": "component", "id": comp_id},
                        meta={
                            "reason": "hash_verification_failed",
                            "pack_id": pack_id
                        }
                    )
                    return
        except ImportError:
            self.diagnostics.record_step(
                phase=phase,
                step_id=f"{phase}.{comp_id}.no_approval_check",
                handler=f"component_phase:{phase}",
                status="skipped",
                target={"kind": "component", "id": comp_id},
                meta={"reason": "approval_manager_not_available", "pack_id": pack_id}
            )
            return
        except Exception as e:
            self.diagnostics.record_step(
                phase=phase,
                step_id=f"{phase}.{comp_id}.approval_check_error",
                handler=f"component_phase:{phase}",
                status="skipped",
                target={"kind": "component", "id": comp_id},
                error=e,
                meta={"reason": "approval_check_failed", "pack_id": pack_id}
            )
            return
        
        if phase == "setup":
            try:
                from .vocab_registry import get_vocab_registry, VOCAB_FILENAME, CONVERTERS_DIRNAME
                vr = get_vocab_registry()
                
                comp_path = Path(getattr(component, "path", "."))
                pack_subdir = comp_path.parent
                
                vocab_result = vr.load_pack_vocab(pack_subdir, pack_id)
                
                if vocab_result["groups"] > 0 or vocab_result["converters"] > 0:
                    self.diagnostics.record_step(
                        phase=phase,
                        step_id=f"{phase}.{comp_id}.vocab_loaded",
                        handler=f"component_phase:{phase}",
                        status="success",
                        meta=vocab_result
                    )
            except Exception as e:
                self.diagnostics.record_step(
                    phase=phase,
                    step_id=f"{phase}.{comp_id}.vocab_warning",
                    handler=f"component_phase:{phase}",
                    status="success",
                    meta={"warning": f"vocab load failed: {e}"}
                )
        
        runtime_dir = Path(getattr(component, "path", "."))
        filename = filename or f"{phase}.py"
        file_path = runtime_dir / filename
        if not file_path.exists():
            self.diagnostics.record_step(phase="startup", step_id=f"{phase}.{comp_id}", handler=f"component_phase:{phase}",
                                          status="skipped", target={"kind": "component", "id": comp_id}, meta={"reason": "file_not_found", "file": str(file_path)})
            return
        ctx = self._build_component_context(phase=phase, component=component)
        try:
            self.diagnostics.record_step(phase="startup", step_id=f"{phase}.{comp_id}.start", handler=f"component_phase:{phase}",
                                          status="success", target={"kind": "component", "id": comp_id}, meta={"file": str(file_path)})
            
            from .secure_executor import get_secure_executor
            executor = get_secure_executor()
            
            # W17-C: freeze env vars around pack execution
            env_snapshot = self._snapshot_env()
            try:
                exec_result = executor.execute_component_phase(
                    pack_id=pack_id,
                    component_id=comp_id,
                    phase=phase,
                    file_path=file_path,
                    context=ctx,
                    component_dir=Path(getattr(component, "path", file_path.parent))
                )
            finally:
                self._restore_env(env_snapshot)
            
            if not exec_result.success:
                raise RuntimeError(exec_result.error or "Secure execution failed")
            
            if exec_result.warnings:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id=f"{phase}.{comp_id}.security_warning",
                    handler=f"component_phase:{phase}",
                    status="success",
                    meta={"execution_mode": exec_result.execution_mode, "warnings": exec_result.warnings}
                )
            
            self.install_journal.append({"ts": self._now_ts(), "event": f"{phase}_run", "scope": "component", "ref": comp_id,
                                          "result": "success", "paths": {"created": [], "modified": []}, 
                                          "meta": {"file": str(file_path), "execution_mode": exec_result.execution_mode}})
            self.diagnostics.record_step(phase="startup", step_id=f"{phase}.{comp_id}.done", handler=f"component_phase:{phase}",
                                          status="success", target={"kind": "component", "id": comp_id}, meta={"file": str(file_path)})
        except Exception as e:
            self._disabled_components_runtime.add(comp_id)
            err = {"type": type(e).__name__, "message": str(e), "trace": self._short_trace()}
            self.install_journal.append({"ts": self._now_ts(), "event": f"{phase}_run", "scope": "component", "ref": comp_id,
                                          "result": "failed", "paths": {"created": [], "modified": []}, "meta": {"file": str(file_path)}, "error": err})
            self.diagnostics.record_step(phase="startup", step_id=f"{phase}.{comp_id}.failed", handler=f"component_phase:{phase}",
                                          status="disabled", target={"kind": "component", "id": comp_id}, error=err, meta={"file": str(file_path)})

    def _short_trace(self) -> str:
        try:
            return traceback.format_exc()[-4000:]
        except Exception:
            return ""

    def _build_component_context(self, phase: str, component: Any) -> Dict[str, Any]:
        reg = self._get_registry()
        active = self._get_active()
        mounts: Dict[str, str] = {}
        try:
            from backend_core.ecosystem.mounts import get_mount_manager
            mounts = {k: str(v) for k, v in get_mount_manager().get_all_mounts().items()}
        except Exception:
            pass
        comp_id = getattr(component, "full_id", None)
        if not isinstance(comp_id, str):
            comp_id = f"{getattr(component,'pack_id',None)}:{getattr(component,'type',None)}:{getattr(component,'id',None)}"
        
        ctx = {"phase": phase, "ts": self._now_ts(),
                "ids": {"component_full_id": comp_id, "component_type": getattr(component, "type", None),
                        "component_id": getattr(component, "id", None), "pack_id": getattr(component, "pack_id", None),
                        "active_pack_identity": getattr(active, "active_pack_identity", None)},
                "paths": {"component_runtime_dir": str(Path(getattr(component, "path", ".")).resolve()), "mounts": mounts},
                "registry": reg, "active_ecosystem": active, "diagnostics": self.diagnostics, "install_journal": self.install_journal,
                "interface_registry": self.interface_registry, "event_bus": self.event_bus, "_source_component": comp_id}
        
        try:
            from .permission_manager import get_permission_manager
            ctx["permission_manager"] = get_permission_manager()
        except ImportError:
            pass
        
        try:
            from .userdata_manager import get_userdata_manager
            ctx["userdata_manager"] = get_userdata_manager()
        except ImportError:
            pass
        
        return ctx

    def _exec_python_file(self, file_path: Path, context: Dict[str, Any]) -> None:
        # W17-C: freeze env vars around direct execution
        env_snapshot = self._snapshot_env()
        try:
            module_name = f"core_runtime_dyn_{file_path.stem}_{abs(hash(str(file_path)))}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec for {file_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            fn = getattr(module, "run", None) or getattr(module, "main", None)
            if fn is None:
                return
            try:
                import inspect
                if len(inspect.signature(fn).parameters) >= 1:
                    fn(context)
                else:
                    fn()
            except Exception:
                raise
        finally:
            self._restore_env(env_snapshot)
