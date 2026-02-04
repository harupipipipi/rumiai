"""
flow_modifier.py - Flow modifier(差し込み)システム

ecosystem/flows/modifiers/*.modifier.yaml を読み込み、
対象Flowに対してステップの注入・置換・削除を行う。

設計原則:
- Flowはファイルからロードされる(setup.py登録に依存しない)
- modifier適用順序は決定的(phase → priority → modifier_id)
- requires(interfaces/capabilities)で適用条件を制御
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from .flow_loader import FlowDefinition, FlowStep, FlowLoadResult


@dataclass
class ModifierRequires:
    """modifier適用条件"""
    interfaces: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)


@dataclass
class FlowModifierDef:
    """Flow modifier定義"""
    modifier_id: str
    target_flow_id: str
    phase: str
    priority: int
    action: str  # inject_before, inject_after, append, replace, remove
    target_step_id: Optional[str]
    step: Optional[Dict[str, Any]]  # 注入/置換するステップ定義
    requires: ModifierRequires
    source_file: Optional[Path] = None
    resolve_target: bool = False  # target_flow_idを共有辞書で解決するか
    resolve_namespace: str = "flow_id"  # 解決に使用するnamespace
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "modifier_id": self.modifier_id,
            "target_flow_id": self.target_flow_id,
            "phase": self.phase,
            "priority": self.priority,
            "action": self.action,
            "target_step_id": self.target_step_id,
            "step": self.step,
            "requires": {
                "interfaces": self.requires.interfaces,
                "capabilities": self.requires.capabilities,
            },
            "_source_file": str(self.source_file) if self.source_file else None,
            "resolve_target": self.resolve_target,
            "resolve_namespace": self.resolve_namespace,
        }


@dataclass
class ModifierLoadResult:
    """modifierロード結果"""
    success: bool
    modifier_id: Optional[str] = None
    modifier_def: Optional[FlowModifierDef] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ModifierApplyResult:
    """modifier適用結果"""
    success: bool
    modifier_id: str
    action: str
    target_flow_id: str
    target_step_id: Optional[str] = None
    skipped_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class FlowModifierLoader:
    """
    Flow modifierローダー
    
    ecosystem/flows/modifiers/*.modifier.yaml を読み込む。
    """
    
    MODIFIERS_DIR = "ecosystem/flows/modifiers"
    
    def __init__(self):
        self._lock = threading.RLock()
        self._loaded_modifiers: Dict[str, FlowModifierDef] = {}
        self._load_errors: List[Dict[str, Any]] = []
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def load_all_modifiers(self) -> Dict[str, FlowModifierDef]:
        """
        全modifierファイルをロード
        
        Returns:
            modifier_id -> FlowModifierDef のマップ
        """
        with self._lock:
            self._loaded_modifiers.clear()
            self._load_errors.clear()
            
            modifiers_dir = Path(self.MODIFIERS_DIR)
            if not modifiers_dir.exists():
                return {}
            
            for yaml_file in sorted(modifiers_dir.glob("*.modifier.yaml")):
                result = self.load_modifier_file(yaml_file)
                
                if result.success and result.modifier_def:
                    if result.modifier_id in self._loaded_modifiers:
                        self._load_errors.append({
                            "file": str(yaml_file),
                            "error": f"Duplicate modifier_id: {result.modifier_id}",
                            "ts": self._now_ts()
                        })
                        continue
                    
                    self._loaded_modifiers[result.modifier_id] = result.modifier_def
                else:
                    self._load_errors.append({
                        "file": str(yaml_file),
                        "errors": result.errors,
                        "ts": self._now_ts()
                    })
            
            return dict(self._loaded_modifiers)
    
    def load_modifier_file(self, file_path: Path) -> ModifierLoadResult:
        """
        単一のmodifierファイルをロード
        """
        result = ModifierLoadResult(success=False)
        
        if not file_path.exists():
            result.errors.append(f"File not found: {file_path}")
            return result
        
        if not HAS_YAML:
            result.errors.append("PyYAML is not installed")
            return result
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.errors.append(f"YAML parse error: {e}")
            return result
        except Exception as e:
            result.errors.append(f"File read error: {e}")
            return result
        
        if not isinstance(raw_data, dict):
            result.errors.append("Modifier file must be a YAML object")
            return result
        
        # 必須フィールドチェック
        modifier_id = raw_data.get("modifier_id")
        if not modifier_id or not isinstance(modifier_id, str):
            result.errors.append("Missing or invalid 'modifier_id'")
            return result
        
        result.modifier_id = modifier_id
        
        target_flow_id = raw_data.get("target_flow_id")
        if not target_flow_id or not isinstance(target_flow_id, str):
            result.errors.append("Missing or invalid 'target_flow_id'")
            return result
        
        phase = raw_data.get("phase")
        if not phase or not isinstance(phase, str):
            result.errors.append("Missing or invalid 'phase'")
            return result
        
        action = raw_data.get("action")
        valid_actions = {"inject_before", "inject_after", "append", "replace", "remove"}
        if not action or action not in valid_actions:
            result.errors.append(f"Invalid 'action': must be one of {valid_actions}")
            return result
        
        # target_step_id(actionによって必須)
        target_step_id = raw_data.get("target_step_id")
        if action in {"inject_before", "inject_after", "replace", "remove"}:
            if not target_step_id or not isinstance(target_step_id, str):
                result.errors.append(f"'target_step_id' is required for action '{action}'")
                return result
        
        # step(inject/append/replaceでは必須)
        step = raw_data.get("step")
        if action in {"inject_before", "inject_after", "append", "replace"}:
            if not step or not isinstance(step, dict):
                result.errors.append(f"'step' is required for action '{action}'")
                return result
            
            # stepの最低限の検証
            if "id" not in step:
                result.errors.append("'step.id' is required")
                return result
            if "type" not in step:
                result.errors.append("'step.type' is required")
                return result
        
        # priority(任意、デフォルト100)
        priority = raw_data.get("priority", 100)
        if not isinstance(priority, (int, float)):
            result.warnings.append("Invalid priority, using 100")
            priority = 100
        priority = int(priority)
        
        # requires(任意)
        requires_raw = raw_data.get("requires", {})
        requires = ModifierRequires(
            interfaces=requires_raw.get("interfaces", []) if isinstance(requires_raw, dict) else [],
            capabilities=requires_raw.get("capabilities", []) if isinstance(requires_raw, dict) else []
        )
        
        # resolve_target（任意）
        resolve_target = raw_data.get("resolve_target", False)
        resolve_namespace = raw_data.get("resolve_namespace", "flow_id")
        
        modifier_def = FlowModifierDef(
            modifier_id=modifier_id,
            target_flow_id=target_flow_id,
            phase=phase,
            priority=priority,
            action=action,
            target_step_id=target_step_id,
            step=step,
            requires=requires,
            source_file=file_path,
            resolve_target=resolve_target,
            resolve_namespace=resolve_namespace,
        )
        
        result.success = True
        result.modifier_def = modifier_def
        return result
    
    def get_loaded_modifiers(self) -> Dict[str, FlowModifierDef]:
        """ロード済みmodifierを取得"""
        with self._lock:
            return dict(self._loaded_modifiers)
    
    def get_load_errors(self) -> List[Dict[str, Any]]:
        """ロードエラーを取得"""
        with self._lock:
            return list(self._load_errors)
    
    def get_modifiers_for_flow(self, flow_id: str, resolve: bool = False) -> List[FlowModifierDef]:
        """
        特定Flowに対するmodifierを取得(ソート済み)
        
        Args:
            flow_id: Flow ID
            resolve: 共有辞書で target_flow_id を解決するか
        
        Returns:
            マッチするmodifierのリスト
        """
        with self._lock:
            modifiers = []
            
            for m in self._loaded_modifiers.values():
                target = m.target_flow_id
                
                # resolve_target が True の場合、共有辞書で解決
                if m.resolve_target or resolve:
                    try:
                        from .shared_dict import get_shared_dict_resolver
                        resolver = get_shared_dict_resolver()
                        target = resolver.resolve(m.resolve_namespace, target)
                    except Exception:
                        pass  # 解決失敗時は元の値を使用
                
                if target == flow_id:
                    modifiers.append(m)
            
            # phase → priority → modifier_id でソート
            return sorted(modifiers, key=lambda m: (m.phase, m.priority, m.modifier_id))


class FlowModifierApplier:
    """
    Flow modifier適用エンジン
    
    modifierをFlowDefinitionに適用する。
    """
    
    def __init__(self, interface_registry=None):
        self._interface_registry = interface_registry
        self._available_interfaces: Set[str] = set()
        self._available_capabilities: Set[str] = set()
    
    def set_interface_registry(self, ir) -> None:
        """InterfaceRegistryを設定"""
        self._interface_registry = ir
        self._refresh_available()
    
    def _refresh_available(self) -> None:
        """利用可能なinterfaces/capabilitiesを更新"""
        if not self._interface_registry:
            return
        
        # interfacesはIRに登録されているキー
        ir_list = self._interface_registry.list() or {}
        self._available_interfaces = set(ir_list.keys())
        
        # capabilitiesはcomponent.capabilitiesから収集
        all_caps = self._interface_registry.get("component.capabilities", strategy="all") or []
        self._available_capabilities = set()
        for cap_dict in all_caps:
            if isinstance(cap_dict, dict):
                for k, v in cap_dict.items():
                    if v:
                        self._available_capabilities.add(k)
    
    def check_requires(self, requires: ModifierRequires) -> Tuple[bool, Optional[str]]:
        """
        requires条件をチェック
        
        Returns:
            (満たされているか, 満たされていない理由)
        """
        # interfaces チェック
        for iface in requires.interfaces:
            if iface not in self._available_interfaces:
                return False, f"interface '{iface}' not available"
        
        # capabilities チェック
        for cap in requires.capabilities:
            if cap not in self._available_capabilities:
                return False, f"capability '{cap}' not available"
        
        return True, None
    
    def apply_modifiers(
        self,
        flow_def: FlowDefinition,
        modifiers: List[FlowModifierDef]
    ) -> Tuple[FlowDefinition, List[ModifierApplyResult]]:
        """
        modifierをFlowに適用
        
        Args:
            flow_def: 元のFlowDefinition
            modifiers: 適用するmodifierリスト(ソート済み)
        
        Returns:
            (変更後のFlowDefinition, 適用結果リスト)
        """
        # FlowDefinitionをディープコピー(元を変更しない)
        new_steps = copy.deepcopy(flow_def.steps)
        results = []
        
        for modifier in modifiers:
            result = self._apply_single_modifier(new_steps, modifier, flow_def.phases)
            results.append(result)
        
        # 新しいFlowDefinitionを作成
        new_flow_def = FlowDefinition(
            flow_id=flow_def.flow_id,
            inputs=copy.deepcopy(flow_def.inputs),
            outputs=copy.deepcopy(flow_def.outputs),
            phases=list(flow_def.phases),
            defaults=copy.deepcopy(flow_def.defaults),
            steps=new_steps,
            source_file=flow_def.source_file,
            source_type=flow_def.source_type
        )
        
        return new_flow_def, results
    
    def _apply_single_modifier(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> ModifierApplyResult:
        """単一のmodifierを適用"""
        result = ModifierApplyResult(
            success=False,
            modifier_id=modifier.modifier_id,
            action=modifier.action,
            target_flow_id=modifier.target_flow_id,
            target_step_id=modifier.target_step_id
        )
        
        # resolve_target が True の場合のログ
        if modifier.resolve_target:
            try:
                from .shared_dict import get_shared_dict_resolver
                resolver = get_shared_dict_resolver()
                resolved = resolver.resolve(modifier.resolve_namespace, modifier.target_flow_id)
                if resolved != modifier.target_flow_id:
                    # 解決された場合は監査ログに記録
                    try:
                        from .audit_logger import get_audit_logger
                        audit = get_audit_logger()
                        audit.log_system_event(
                            event_type="modifier_target_resolved",
                            success=True,
                            details={
                                "modifier_id": modifier.modifier_id,
                                "original_target": modifier.target_flow_id,
                                "resolved_target": resolved,
                                "namespace": modifier.resolve_namespace,
                            }
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        
        # requires チェック
        satisfied, reason = self.check_requires(modifier.requires)
        if not satisfied:
            result.skipped_reason = reason
            return result
        
        # phaseがFlowに存在するかチェック
        if modifier.phase not in phases:
            result.skipped_reason = f"phase '{modifier.phase}' not in flow phases"
            return result
        
        try:
            if modifier.action == "append":
                self._action_append(steps, modifier, phases)
            elif modifier.action == "inject_before":
                self._action_inject_before(steps, modifier, phases)
            elif modifier.action == "inject_after":
                self._action_inject_after(steps, modifier, phases)
            elif modifier.action == "replace":
                self._action_replace(steps, modifier, phases)
            elif modifier.action == "remove":
                self._action_remove(steps, modifier)
            else:
                result.errors.append(f"Unknown action: {modifier.action}")
                return result
            
            result.success = True
        except Exception as e:
            result.errors.append(str(e))
        
        # 監査ログに記録
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_modifier_application(
                modifier_id=modifier.modifier_id,
                target_flow_id=modifier.target_flow_id,
                action=modifier.action,
                success=result.success,
                target_step_id=modifier.target_step_id,
                skipped_reason=result.skipped_reason,
                error=result.errors[0] if result.errors else None
            )
        except Exception:
            pass  # 監査ログのエラーで処理を止めない
        
        return result
    
    def _step_from_dict(self, step_dict: Dict[str, Any], phase: str, modifier_id: str) -> FlowStep:
        """辞書からFlowStepを作成"""
        return FlowStep(
            id=step_dict.get("id", f"modifier_{modifier_id}"),
            phase=step_dict.get("phase", phase),
            priority=step_dict.get("priority", 100),
            type=step_dict.get("type", "handler"),
            when=step_dict.get("when"),
            input=step_dict.get("input"),
            output=step_dict.get("output"),
            raw=step_dict,
            owner_pack=step_dict.get("owner_pack"),
            file=step_dict.get("file"),
            timeout_seconds=step_dict.get("timeout_seconds", 60.0)
        )
    
    def _find_step_index(self, steps: List[FlowStep], step_id: str) -> int:
        """step_idでステップのインデックスを検索"""
        for i, step in enumerate(steps):
            if step.id == step_id:
                return i
        return -1
    
    def _action_append(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> None:
        """append: 指定phaseの最後(次のphaseの直前)にステップを追加"""
        new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
        
        # 次のphaseの直前(=このphaseの末尾)を探す
        insert_index = len(steps)
        phase_order = {p: i for i, p in enumerate(phases)}
        target_phase_order = phase_order.get(modifier.phase, 999)
        
        for i, step in enumerate(steps):
            step_phase_order = phase_order.get(step.phase, 999)
            if step_phase_order > target_phase_order:
                insert_index = i
                break
        
        steps.insert(insert_index, new_step)
    
    def _action_inject_before(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> None:
        """inject_before: target_step_idの前にステップを挿入"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            raise ValueError(f"Target step '{modifier.target_step_id}' not found")
        
        new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
        steps.insert(target_index, new_step)
    
    def _action_inject_after(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> None:
        """inject_after: target_step_idの後にステップを挿入"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            raise ValueError(f"Target step '{modifier.target_step_id}' not found")
        
        new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
        steps.insert(target_index + 1, new_step)
    
    def _action_replace(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> None:
        """replace: target_step_idのステップを置換"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            raise ValueError(f"Target step '{modifier.target_step_id}' not found")
        
        new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
        steps[target_index] = new_step
    
    def _action_remove(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef
    ) -> None:
        """remove: target_step_idのステップを削除"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            raise ValueError(f"Target step '{modifier.target_step_id}' not found")
        
        steps.pop(target_index)


# グローバルインスタンス
_global_modifier_loader: Optional[FlowModifierLoader] = None
_global_modifier_applier: Optional[FlowModifierApplier] = None
_modifier_lock = threading.Lock()


def get_modifier_loader() -> FlowModifierLoader:
    """グローバルなFlowModifierLoaderを取得"""
    global _global_modifier_loader
    if _global_modifier_loader is None:
        with _modifier_lock:
            if _global_modifier_loader is None:
                _global_modifier_loader = FlowModifierLoader()
    return _global_modifier_loader


def get_modifier_applier() -> FlowModifierApplier:
    """グローバルなFlowModifierApplierを取得"""
    global _global_modifier_applier
    if _global_modifier_applier is None:
        with _modifier_lock:
            if _global_modifier_applier is None:
                _global_modifier_applier = FlowModifierApplier()
    return _global_modifier_applier


def reset_modifier_loader() -> FlowModifierLoader:
    """FlowModifierLoaderをリセット(テスト用)"""
    global _global_modifier_loader
    with _modifier_lock:
        _global_modifier_loader = FlowModifierLoader()
    return _global_modifier_loader


def reset_modifier_applier() -> FlowModifierApplier:
    """FlowModifierApplierをリセット(テスト用)"""
    global _global_modifier_applier
    with _modifier_lock:
        _global_modifier_applier = FlowModifierApplier()
    return _global_modifier_applier
