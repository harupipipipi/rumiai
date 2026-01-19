"""
component_lifecycle.py - Component Lifecycle Executor(dependency/setup/runtime/assets/addon実行器)

Step1では「器」だけ確定する。
実際のecosystem連携と規約実行はStep6で実装する。
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict, List, Iterable, Tuple, Set

from .diagnostics import Diagnostics
from .install_journal import InstallJournal


@dataclass
class ComponentLifecycleExecutor:
    """
    コンポーネントのライフサイクルを実行する。

    実行フェーズ(確定仕様):
    - dependency(dependency_manager.py があれば実行)
    - setup(setup.py があれば実行)
    - runtime_boot
    - assets_load
    - addon_apply
    """

    diagnostics: Diagnostics
    install_journal: InstallJournal

    # ecosystem側の参照(遅延注入/遅延取得OK)
    registry: Optional[Any] = None
    active_ecosystem: Optional[Any] = None

    # Kernel側から注入されると便利(必須ではない：贔屓禁止のため)
    interface_registry: Optional[Any] = None
    event_bus: Optional[Any] = None

    # 実行時に無効化されたもの(永続設定は変更しない)
    _disabled_components_runtime: Set[str] = field(default_factory=set)

    def _now_ts(self) -> str:
        # Diagnostics側にも now はあるが、ここは独立して持つ(依存を減らす)
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ---------------------------
    # Ecosystem access helpers
    # ---------------------------

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

    # ---------------------------
    # Component selection policy
    # ---------------------------

    def iter_active_components(self, phase: Optional[str] = None) -> List[Any]:
        """
        active pack + disabled(+必要ならoverrides)を反映し、実行対象コンポーネントを列挙する。

        方針(OS的/贔屓回避/限界を設定しない):
        - active_pack_identity の pack を優先
        - packが見つからない場合は registryの最初のpackへフォールバック

        重要(今回の修正ポイント):
        - dependency/setup は「そのコンポーネントが選抜されるかどうか」と無関係に
          **Pack内の全コンポーネントに対して走ってよいフェーズ**。
          したがって、dependency/setup では typeごとに1つへ絞らず、全件列挙する。
        - runtime_boot/assets_load 等の"提供物を選ぶ"フェーズでのみ、
          overrides を使った選抜(typeごとに1つ)を行う余地がある(将来)。
        """
        reg = self._get_registry()
        active = self._get_active()

        # pack選択：active pack優先、無ければ最初のpack
        pack = None
        try:
            pack = reg.get_pack_by_identity(active.active_pack_identity)
        except Exception:
            pack = None
        if pack is None:
            # フォールバック：最初のpack
            if getattr(reg, "packs", None):
                pack = list(reg.packs.values())[0]
        if pack is None:
            return []

        # pack.components は { "type:id": ComponentInfo }
        comps: List[Any] = list(getattr(pack, "components", {}).values())
        if not comps:
            return []

        disabled_persistent: Set[str] = set()
        try:
            cfg = active.config
            disabled_persistent = set(getattr(cfg, "disabled_components", []) or [])
        except Exception:
            disabled_persistent = set()

        # phaseがdependency/setupなら「全件」を返す(ただしdisabledは除外)
        # phaseがNoneまたは将来の選抜フェーズなら、ひとまず全件(将来選抜ロジックを追加可能)
        phase_name = (phase or "").strip()

        # 決定的順序(再現性のため)
        comps_sorted = sorted(
            comps,
            key=lambda x: (
                getattr(x, "pack_id", ""),
                getattr(x, "type", ""),
                getattr(x, "id", ""),
                getattr(x, "version", ""),
            ),
        )

        active_list: List[Any] = []
        for c in comps_sorted:
            full_id = getattr(c, "full_id", None)
            comp_full_id = full_id if isinstance(full_id, str) else f"{getattr(c,'pack_id',None)}:{getattr(c,'type',None)}:{getattr(c,'id',None)}"

            if isinstance(comp_full_id, str) and comp_full_id in disabled_persistent:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="component.filter",
                    handler="component_lifecycle:filter",
                    status="skipped",
                    target={"kind": "component", "id": comp_full_id},
                    meta={"reason": "disabled_persistent", "phase": phase_name},
                )
                continue

            if isinstance(comp_full_id, str) and comp_full_id in self._disabled_components_runtime:
                self.diagnostics.record_step(
                    phase="startup",
                    step_id="component.filter",
                    handler="component_lifecycle:filter",
                    status="skipped",
                    target={"kind": "component", "id": comp_full_id},
                    meta={"reason": "disabled_runtime", "phase": phase_name},
                )
                continue

            active_list.append(c)

        return active_list

    # ---------------------------
    # Phase execution
    # ---------------------------

    def run_phase(self, phase_name: str) -> Dict[str, Any]:
        """
        フェーズ実行:
        - dependency: dependency_manager.py があれば実行
        - setup: setup.py があれば実行(冪等前提)
        - runtime_boot: runtime_boot.py があれば実行
        - その他: 今はskippedとして診断に残す(後工程で実装)
        """
        phase = (phase_name or "").strip()
        if phase not in ("dependency", "setup", "runtime_boot"):
            # 後工程の器：現時点では no-op だが記録は残す
            self.diagnostics.record_step(
                phase="startup",
                step_id=f"component_phase.{phase}",
                handler=f"component_phase:{phase}",
                status="skipped",
                target={"kind": "none", "id": None},
                meta={"reason": "not_implemented_yet"},
            )
            return {
                "_kernel_step_status": "skipped",
                "_kernel_step_meta": {"phase": phase, "reason": "not_implemented_yet"},
            }

        components = self.iter_active_components(phase=phase)
        self._ensure_components_on_syspath(components)
        self.diagnostics.record_step(
            phase="startup",
            step_id=f"component_phase.{phase}.start",
            handler=f"component_phase:{phase}",
            status="success",
            target={"kind": "none", "id": None},
            meta={"count": len(components)},
        )

        before_disabled = set(self._disabled_components_runtime)
        for comp in components:
            self._run_phase_for_component(phase, comp)
        after_disabled = set(self._disabled_components_runtime)
        newly_disabled = sorted(list(after_disabled - before_disabled))

        self.diagnostics.record_step(
            phase="startup",
            step_id=f"component_phase.{phase}.end",
            handler=f"component_phase:{phase}",
            status="success",
            target={"kind": "none", "id": None},
            meta={"disabled_runtime_count": len(self._disabled_components_runtime)},
        )

        # Kernelへ「無効化ターゲット」を返す(fail-softの実体化)
        disable_targets = [{"kind": "component", "id": cid} for cid in newly_disabled]
        return {
            "_kernel_step_status": "success",
            "_kernel_step_meta": {
                "phase": phase,
                "count": len(components),
                "newly_disabled": newly_disabled,
            },
            "_kernel_disable_targets": disable_targets,
        }

    def _run_phase_for_component(self, phase: str, component: Any) -> None:
        full_id = getattr(component, "full_id", None)
        comp_id = full_id if isinstance(full_id, str) else f"{getattr(component,'pack_id',None)}:{getattr(component,'type',None)}:{getattr(component,'id',None)}"
        runtime_dir = Path(getattr(component, "path", "."))

        if phase == "dependency":
            filename = "dependency_manager.py"
        elif phase == "setup":
            filename = "setup.py"
        else:  # runtime_boot
            filename = "runtime_boot.py"
        file_path = runtime_dir / filename

        if not file_path.exists():
            self.diagnostics.record_step(
                phase="startup",
                step_id=f"{phase}.{comp_id}",
                handler=f"component_phase:{phase}",
                status="skipped",
                target={"kind": "component", "id": comp_id},
                meta={"reason": "file_not_found", "file": str(file_path)},
            )
            return

        # 実行コンテキスト(多め：コミュニティが強い拡張を書ける)
        ctx = self._build_component_context(phase=phase, component=component)

        try:
            self.diagnostics.record_step(
                phase="startup",
                step_id=f"{phase}.{comp_id}.start",
                handler=f"component_phase:{phase}",
                status="success",
                target={"kind": "component", "id": comp_id},
                meta={"file": str(file_path)},
            )

            self._exec_python_file(file_path, ctx)

            # journal(成功)
            self.install_journal.append({
                "ts": self._now_ts(),
                "event": f"{phase}_run",
                "scope": "component",
                "ref": comp_id,
                "result": "success",
                "paths": {"created": [], "modified": []},
                "meta": {"file": str(file_path)},
            })

            self.diagnostics.record_step(
                phase="startup",
                step_id=f"{phase}.{comp_id}.done",
                handler=f"component_phase:{phase}",
                status="success",
                target={"kind": "component", "id": comp_id},
                meta={"file": str(file_path)},
            )

        except Exception as e:
            # fail-soft：このcomponentをruntime上無効化して続行
            self._disabled_components_runtime.add(comp_id)

            err = {
                "type": type(e).__name__,
                "message": str(e),
                "trace": self._short_trace(),
            }

            # journal(失敗)
            self.install_journal.append({
                "ts": self._now_ts(),
                "event": f"{phase}_run",
                "scope": "component",
                "ref": comp_id,
                "result": "failed",
                "paths": {"created": [], "modified": []},
                "meta": {"file": str(file_path)},
                "error": err,
            })

            self.diagnostics.record_step(
                phase="startup",
                step_id=f"{phase}.{comp_id}.failed",
                handler=f"component_phase:{phase}",
                status="disabled",
                target={"kind": "component", "id": comp_id},
                error=err,
                meta={"file": str(file_path), "reason": "phase_failed_fail_soft"},
            )

    def _ensure_components_on_syspath(self, components: list) -> None:
        """
        アクティブコンポーネントの runtime_dir を sys.path に追加（贔屓なし・汎用）。
        これにより component が他 component の Python package を import できる。
        """
        import sys
        try:
            for comp in components:
                p = str(Path(getattr(comp, "path", ".")).resolve())
                if p and p not in sys.path:
                    sys.path.insert(0, p)
        except Exception:
            # fail-soft
            return

    def _short_trace(self) -> str:
        """
        診断用の短縮トレース(長すぎないようにする)。
        """
        try:
            tb = traceback.format_exc()
            # 最大 4000 文字程度に制限
            return tb[-4000:]
        except Exception:
            return ""

    def _build_component_context(self, phase: str, component: Any) -> Dict[str, Any]:
        """
        dependency_manager.py / setup.py に渡す context(多め)。
        - Kernelが特定概念を贔屓しない一方で、拡張作者が高度なことをできるようにする。
        """
        reg = self._get_registry()
        active = self._get_active()

        # mounts(存在しない可能性もあるのでfail-soft)
        mounts: Dict[str, str] = {}
        try:
            from backend_core.ecosystem.mounts import get_mount_manager
            mm = get_mount_manager()
            mounts = {k: str(v) for k, v in mm.get_all_mounts().items()}
        except Exception:
            mounts = {}

        comp_id = getattr(component, "full_id", None)
        if not isinstance(comp_id, str):
            comp_id = f"{getattr(component,'pack_id',None)}:{getattr(component,'type',None)}:{getattr(component,'id',None)}"

        return {
            "phase": phase,
            "ts": self._now_ts(),
            "ids": {
                "component_full_id": comp_id,
                "component_type": getattr(component, "type", None),
                "component_id": getattr(component, "id", None),
                "pack_id": getattr(component, "pack_id", None),
                "active_pack_identity": getattr(active, "active_pack_identity", None),
            },
            "paths": {
                "component_runtime_dir": str(Path(getattr(component, "path", ".")).resolve()),
                "mounts": mounts,
            },
            "registry": reg,
            "active_ecosystem": active,
            "diagnostics": self.diagnostics,
            "install_journal": self.install_journal,
            "interface_registry": self.interface_registry,
            "event_bus": self.event_bus,
        }

    def _exec_python_file(self, file_path: Path, context: Dict[str, Any]) -> None:
        """
        pythonファイルをロードして規約関数を呼ぶ。

        呼び出し規約(固定):
        - run(context) があれば優先
        - main(context) があれば次点
        - どちらも無ければ import 副作用のみ(成功扱い)
        """
        module_name = f"core_runtime_dyn_{file_path.stem}_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        # 規約関数の探索
        fn = None
        if hasattr(module, "run") and callable(getattr(module, "run")):
            fn = getattr(module, "run")
        elif hasattr(module, "main") and callable(getattr(module, "main")):
            fn = getattr(module, "main")

        if fn is None:
            return

        # signature互換：引数なし/引数あり両方許容
        try:
            import inspect
            sig = inspect.signature(fn)
            if len(sig.parameters) >= 1:
                fn(context)
            else:
                fn()
        except Exception:
            # ここでの例外は上位でfail-soft処理される
            raise
