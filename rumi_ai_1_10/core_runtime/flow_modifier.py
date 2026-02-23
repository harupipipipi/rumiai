"""
flow_modifier.py - Flow modifier(差し込み)システム

ecosystem/packs/{pack_id}/backend/flows/modifiers/*.modifier.yaml を読み込み、
対象Flowに対してステップの注入・置換・削除を行う。

設計原則:
- shared modifiers (user_data/shared/flows/modifiers/) は承認不要でロード
- pack提供 modifiers は承認済み+ハッシュ一致のpackのみロード
- local_pack互換 は deprecated（優先順位最低）
- pack_subdir 基準で flows/modifiers/ と backend/flows/modifiers/ の両方を探索
- modifier適用順序は決定的
- 同一注入点: priority → step.id → modifier_id
- inject相対位置を保持（再ソート禁止）

Phase2追加:
- pack配下探索 (ecosystem/packs/{pack_id}/backend/flows/modifiers/)
- 承認ゲート (ApprovalManager連携)
- local_pack互換

Phase3追加:
- modifier適用の決定性強化
- 同一注入点での順序: priority → step.id → modifier_id
- inject相対位置を保持（再ソート禁止）

PR-B追加:
- hash_mismatch検知時にMODIFIED昇格 + network権限無効化（B3）

パス刷新:
- pack_subdir 基準で modifiers 探索候補を複数化
- user_data/shared/flows/modifiers/ を shared source として追加

PR-C追加:
- _step_from_dict で principal_id を FlowStep に引き継ぎ（Capability Proxy連携）

Wave 9追加:
- FlowModifierDef に conflicts_with / compatible_with フィールド追加
- apply_modifiers() に Modifier 衝突検出を追加（警告のみ、動作変更なし）
"""

from __future__ import annotations

import copy
import logging
import os
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

logger = logging.getLogger(__name__)

import fnmatch

from .flow_loader import FlowDefinition, FlowStep, FlowLoadResult


from .paths import (
    LOCAL_PACK_ID,
    LOCAL_PACK_DIR,
    LOCAL_PACK_MODIFIERS_DIR,
    ECOSYSTEM_DIR,
    discover_pack_locations,
    get_pack_modifier_dirs,
    get_shared_modifier_dir,
)


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
    source_pack_id: Optional[str] = None  # 提供元pack_id
    resolve_target: bool = False  # target_flow_idを共有辞書で解決するか
    resolve_namespace: str = "flow_id"  # 解決に使用するnamespace
    conflicts_with: Optional[List[str]] = None  # Wave 9: 衝突宣言
    compatible_with: Optional[List[str]] = None  # Wave 9: 互換性宣言

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
            "_source_pack_id": self.source_pack_id,
            "resolve_target": self.resolve_target,
            "resolve_namespace": self.resolve_namespace,
            "conflicts_with": self.conflicts_with,
            "compatible_with": self.compatible_with,
        }


@dataclass
class ModifierLoadResult:
    """modifierロード結果"""
    success: bool
    modifier_id: Optional[str] = None
    modifier_def: Optional[FlowModifierDef] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None


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


@dataclass
class ModifierSkipRecord:
    """スキップされたmodifierの記録"""
    file_path: str
    pack_id: Optional[str]
    reason: str
    ts: str


class FlowModifierLoader:
    """
    Flow modifierローダー

    探索優先順:
      1. user_data/shared/flows/modifiers/ — 承認不要
      2. pack提供 modifiers — 承認+ハッシュ一致のpackのみ
      3. local_pack互換 ecosystem/flows/modifiers/ — deprecated

    承認済み+ハッシュ一致のpackのみ対象。
    """

    def __init__(self, approval_manager=None):
        self._lock = threading.RLock()
        self._loaded_modifiers: Dict[str, FlowModifierDef] = {}
        self._load_errors: List[Dict[str, Any]] = []
        self._skipped_modifiers: List[ModifierSkipRecord] = []
        self._approval_manager = approval_manager

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _get_approval_manager(self):
        """ApprovalManagerを取得（遅延初期化）"""
        if self._approval_manager is None:
            try:
                from .approval_manager import get_approval_manager
                self._approval_manager = get_approval_manager()
            except Exception:
                pass
        return self._approval_manager

    def _is_local_pack_mode_enabled(self) -> bool:
        """local_packモードが有効かチェック"""
        mode = os.environ.get("RUMI_LOCAL_PACK_MODE", "off").lower()
        return mode == "require_approval"

    def _check_pack_approval(self, pack_id: str) -> Tuple[bool, Optional[str]]:
        """
        packの承認状態をチェック

        PR-B追加: hash_mismatch検知時にMODIFIED昇格 + network権限無効化

        Returns:
            (is_approved: bool, skip_reason: Optional[str])
        """
        am = self._get_approval_manager()
        if am is None:
            # ApprovalManagerがない場合は承認済みとみなす（後方互換）
            return True, None

        try:
            is_valid, reason = am.is_pack_approved_and_verified(pack_id)

            # B3: hash_mismatch検知時の処理
            if not is_valid and reason == "hash_mismatch":
                self._handle_hash_mismatch(pack_id, am)

            return is_valid, reason
        except Exception as e:
            return False, f"approval_check_error: {e}"

    def _handle_hash_mismatch(self, pack_id: str, am) -> None:
        """
        hash_mismatch検知時の処理（B3）

        - ApprovalManager.mark_modified() を呼ぶ（必須）
        - NetworkGrantManager.disable_for_modified() も呼ぶ（best-effort）
        """
        # 1. MODIFIEDへ昇格（必須）
        try:
            am.mark_modified(pack_id)
        except Exception as e:
            # 失敗してもログに記録して継続
            self._log_hash_mismatch_error(pack_id, "mark_modified", e)

        # 2. ネットワーク権限無効化（best-effort）
        try:
            from .network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            ngm.disable_for_modified(pack_id)
        except Exception as e:
            # 失敗してもログに記録して継続（best-effort）
            self._log_hash_mismatch_error(pack_id, "disable_network", e)

    def _log_hash_mismatch_error(self, pack_id: str, operation: str, error: Exception) -> None:
        """hash_mismatch処理のエラーをログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="hash_mismatch_handling_error",
                success=False,
                details={
                    "pack_id": pack_id,
                    "operation": operation,
                    "error": str(error),
                }
            )
        except Exception:
            pass  # 監査ログのエラーで処理を止めない

    def _record_skip(self, file_path: Path, pack_id: Optional[str], reason: str) -> None:
        """スキップを記録"""
        record = ModifierSkipRecord(
            file_path=str(file_path),
            pack_id=pack_id,
            reason=reason,
            ts=self._now_ts()
        )
        self._skipped_modifiers.append(record)

        # 監査ログにも記録
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="modifier_load_skipped",
                success=False,
                details={
                    "file": str(file_path),
                    "pack_id": pack_id,
                    "reason": reason,
                }
            )
        except Exception:
            pass

    def load_all_modifiers(self) -> Dict[str, FlowModifierDef]:
        """
        全modifierファイルをロード

        探索優先順:
          1. shared modifiers (user_data/shared/flows/modifiers/) — 承認不要
          2. pack提供 modifiers — 承認必須
          3. local_pack互換 — deprecated

        Returns:
            modifier_id -> FlowModifierDef のマップ
        """
        with self._lock:
            self._loaded_modifiers.clear()
            self._load_errors.clear()
            self._skipped_modifiers.clear()

            # 1. shared modifierをロード（承認不要）
            self._load_shared_modifiers()

            # 2. pack提供modifierをロード（承認必須）
            self._load_pack_modifiers_via_discovery()

            # 3. local_pack互換（環境変数で制御、deprecated）
            if self._is_local_pack_mode_enabled():
                self._load_local_pack_modifiers()

            return dict(self._loaded_modifiers)

    def _load_shared_modifiers(self) -> None:
        """
        shared modifierをロード（承認不要）
        user_data/shared/flows/modifiers/**/*.modifier.yaml を読み込む。
        """
        shared_dir = get_shared_modifier_dir()
        if not shared_dir.exists():
            return
        self._load_directory_modifiers(shared_dir, None)

    def _load_pack_modifiers_via_discovery(self) -> None:
        """
        pack提供modifierをロード（承認必須）

        discover_pack_locations() で検出された全packについて、
        pack_subdir 基準で modifiers ディレクトリを探索する。
        """
        locations = discover_pack_locations(str(ECOSYSTEM_DIR))

        for loc in locations:
            pack_id = loc.pack_id

            # 承認チェック
            is_approved, reason = self._check_pack_approval(pack_id)
            if not is_approved:
                for mod_dir in get_pack_modifier_dirs(loc.pack_subdir):
                    for yaml_file in sorted(mod_dir.glob("**/*.modifier.yaml")):
                        self._record_skip(yaml_file, pack_id, reason or "not_approved")
                continue

            # pack_subdir 基準で候補ディレクトリを探索
            for mod_dir in get_pack_modifier_dirs(loc.pack_subdir):
                self._load_directory_modifiers(mod_dir, pack_id)

    def _load_local_pack_modifiers(self) -> None:
        """local_pack互換: ecosystem/flows/modifiers/ をロード（deprecated）"""
        is_approved, reason = self._check_pack_approval(LOCAL_PACK_ID)
        if not is_approved:
            local_modifiers_dir = Path(LOCAL_PACK_MODIFIERS_DIR)
            if local_modifiers_dir.exists():
                for yaml_file in local_modifiers_dir.glob("**/*.modifier.yaml"):
                    self._record_skip(yaml_file, LOCAL_PACK_ID, reason or "not_approved")
            return

        # deprecated 警告
        import sys
        print(
            "[FlowModifierLoader] WARNING: local_pack modifiers "
            "(ecosystem/flows/modifiers/) is deprecated. "
            "Use user_data/shared/flows/modifiers/ instead.",
            file=sys.stderr,
        )

        local_modifiers_dir = Path(LOCAL_PACK_MODIFIERS_DIR)
        if local_modifiers_dir.exists():
            self._load_directory_modifiers(local_modifiers_dir, LOCAL_PACK_ID)

    def _load_directory_modifiers(self, directory: Path, pack_id: str) -> None:
        """ディレクトリ内のmodifierファイルをロード"""
        for yaml_file in sorted(directory.glob("**/*.modifier.yaml")):
            result = self.load_modifier_file(yaml_file, pack_id)

            if result.success and result.modifier_def:
                if result.modifier_id in self._loaded_modifiers:
                    self._load_errors.append({
                        "file": str(yaml_file),
                        "error": f"Duplicate modifier_id: {result.modifier_id}",
                        "ts": self._now_ts()
                    })
                    continue

                self._loaded_modifiers[result.modifier_id] = result.modifier_def

                # #61: ワイルドカード Modifier 警告
                if result.modifier_def.target_flow_id == "*":
                    logger.warning(
                        "[FlowModifier] Modifier '%s' targets ALL flows (target_flow_id='*'). "
                        "This modifier will be applied to every flow.",
                        result.modifier_id,
                    )
                    try:
                        from .audit_logger import get_audit_logger
                        audit = get_audit_logger()
                        audit.log_system_event(
                            event_type="wildcard_modifier_loaded",
                            success=True,
                            details={
                                "modifier_id": result.modifier_id,
                                "source_pack_id": result.modifier_def.source_pack_id,
                                "warning": "This modifier applies to ALL flows",
                            }
                        )
                    except Exception:
                        pass
            else:
                self._load_errors.append({
                    "file": str(yaml_file),
                    "errors": result.errors,
                    "ts": self._now_ts()
                })

    def load_modifier_file(self, file_path: Path, pack_id: Optional[str] = None) -> ModifierLoadResult:
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

        # Wave 9: conflicts_with / compatible_with（任意）
        conflicts_with_raw = raw_data.get("conflicts_with")
        conflicts_with = None
        if isinstance(conflicts_with_raw, list):
            conflicts_with = [str(x) for x in conflicts_with_raw if x]

        compatible_with_raw = raw_data.get("compatible_with")
        compatible_with = None
        if isinstance(compatible_with_raw, list):
            compatible_with = [str(x) for x in compatible_with_raw if x]

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
            source_pack_id=pack_id,
            resolve_target=resolve_target,
            resolve_namespace=resolve_namespace,
            conflicts_with=conflicts_with,
            compatible_with=compatible_with,
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

    def get_skipped_modifiers(self) -> List[ModifierSkipRecord]:
        """スキップされたmodifierを取得"""
        with self._lock:
            return list(self._skipped_modifiers)

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

                # C6: fnmatch pattern matching for wildcard target_flow_id
                if fnmatch.fnmatch(flow_id, target):
                    modifiers.append(m)

            # phase → priority → modifier_id でソート
            return sorted(modifiers, key=lambda m: (m.phase, m.priority, m.modifier_id))


class FlowModifierApplier:
    """
    Flow modifier適用エンジン

    modifierをFlowDefinitionに適用する。

    Phase3: 適用決定性の強化
    - 同一注入点での順序: priority → step.id → modifier_id
    - inject相対位置を保持（再ソートしない）
    """

    def __init__(self, interface_registry=None, dry_run: bool = False):
        self._interface_registry = interface_registry
        self._available_interfaces: Set[str] = set()
        self._available_capabilities: Set[str] = set()
        self._dry_run = dry_run

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

    # ------------------------------------------------------------------
    # Wave 9: Modifier 衝突検出
    # ------------------------------------------------------------------

    def _detect_conflicts(
        self,
        modifiers: List[FlowModifierDef],
        results: List[ModifierApplyResult],
    ) -> None:
        """
        同一 target_step_id に対して複数の Modifier が作用する場合の衝突を検出し、
        診断ログ（logger.warning）と監査ログ（audit_logger）に警告を出す。

        - remove + replace/inject_* が同一 target_step_id に作用する場合は強い警告
        - conflicts_with / compatible_with フィールドによる矛盾チェック

        この関数は警告を出すだけで、既存動作を変更しない。
        """
        # results に含まれるスキップ済み modifier_id を除外
        skipped_ids = {r.modifier_id for r in results if r.skipped_reason}

        # 有効な modifier のみ対象
        active_modifiers = [m for m in modifiers if m.modifier_id not in skipped_ids]

        # target_step_id ごとにグループ化
        by_target: Dict[str, List[FlowModifierDef]] = {}
        for m in active_modifiers:
            tsid = m.target_step_id
            if tsid:
                if tsid not in by_target:
                    by_target[tsid] = []
                by_target[tsid].append(m)

        # 1. 同一 target_step_id に複数 Modifier が作用する場合の警告
        for tsid, group in by_target.items():
            if len(group) < 2:
                continue

            actions = {m.action for m in group}
            modifier_ids = [m.modifier_id for m in group]

            has_remove = "remove" in actions
            has_mutating = actions & {"replace", "inject_before", "inject_after"}

            if has_remove and has_mutating:
                # 強い警告: remove と inject/replace が同一 target に作用
                msg = (
                    "[FlowModifier] CONFLICT (severe): target_step_id '%s' "
                    "has both 'remove' and %s actions from "
                    "modifiers %s. Injecting/replacing a removed step "
                    "is likely unintended."
                )
                logger.warning(msg, tsid, sorted(has_mutating), modifier_ids)
                self._audit_conflict(tsid, modifier_ids, sorted(actions), severity="severe")
            else:
                # 通常の警告: 複数 Modifier が同一 target に作用
                msg = (
                    "[FlowModifier] CONFLICT (info): target_step_id '%s' "
                    "is targeted by multiple modifiers %s "
                    "with actions %s."
                )
                logger.warning(msg, tsid, modifier_ids, sorted(actions))
                self._audit_conflict(tsid, modifier_ids, sorted(actions), severity="info")

        # 2. conflicts_with / compatible_with による矛盾チェック
        active_ids = {m.modifier_id for m in active_modifiers}
        for m in active_modifiers:
            if m.conflicts_with:
                for cid in m.conflicts_with:
                    if cid in active_ids:
                        msg = (
                            "[FlowModifier] CONFLICT (declared): modifier '%s' "
                            "declares conflicts_with '%s', but both are active."
                        )
                        logger.warning(msg, m.modifier_id, cid)
                        self._audit_conflict(
                            m.target_step_id or "(global)",
                            [m.modifier_id, cid],
                            ["conflicts_with"],
                            severity="declared",
                        )
            if m.compatible_with:
                for cid in m.compatible_with:
                    if cid not in active_ids and cid != m.modifier_id:
                        msg = (
                            "[FlowModifier] CONFLICT (compatibility): modifier '%s' "
                            "declares compatible_with '%s', but '%s' is not active."
                        )
                        logger.warning(msg, m.modifier_id, cid, cid)
                        self._audit_conflict(
                            m.target_step_id or "(global)",
                            [m.modifier_id, cid],
                            ["compatible_with_missing"],
                            severity="compatibility",
                        )

    def _audit_conflict(
        self,
        target_step_id: str,
        modifier_ids: List[str],
        actions: List[str],
        severity: str = "info",
    ) -> None:
        """衝突を監査ログに記録（best-effort）"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="modifier_conflict_detected",
                success=True,
                details={
                    "target_step_id": target_step_id,
                    "modifier_ids": modifier_ids,
                    "actions": actions,
                    "severity": severity,
                },
            )
        except Exception:
            pass

    # ------------------------------------------------------------------

    def apply_modifiers(
        self,
        flow_def: FlowDefinition,
        modifiers: List[FlowModifierDef]
    ) -> Tuple[FlowDefinition, List[ModifierApplyResult]]:
        """
        modifierをFlowに適用

        Phase3: 決定的な適用順序
        - 同一注入点(target_step_id + action)でバッファリング
        - バッファ内を priority → step.id → modifier_id でソート
        - 同一注入点のステップは一括挿入してインデックスずれを防ぐ

        Args:
            flow_def: 元のFlowDefinition
            modifiers: 適用するmodifierリスト(ソート済み)

        Returns:
            (変更後のFlowDefinition, 適用結果リスト)
        """
        # FlowDefinitionをディープコピー(元を変更しない)
        new_steps = copy.deepcopy(flow_def.steps)
        results = []

        # Phase3: 注入点ごとにmodifierをグループ化
        inject_before_groups: Dict[str, List[FlowModifierDef]] = {}
        inject_after_groups: Dict[str, List[FlowModifierDef]] = {}
        append_groups: Dict[str, List[FlowModifierDef]] = {}
        other_modifiers: List[FlowModifierDef] = []

        for modifier in modifiers:
            # requires チェックを先に行う
            satisfied, reason = self.check_requires(modifier.requires)
            if not satisfied:
                result = ModifierApplyResult(
                    success=False,
                    modifier_id=modifier.modifier_id,
                    action=modifier.action,
                    target_flow_id=modifier.target_flow_id,
                    target_step_id=modifier.target_step_id,
                    skipped_reason=f"requires_not_satisfied: {reason}"
                )
                self._log_modifier_skip(modifier, result.skipped_reason)
                results.append(result)
                continue

            # phaseチェック
            if modifier.phase not in flow_def.phases:
                # #8: append で phase 未存在の場合、最後の phase にフォールバック
                if modifier.action == "append" and flow_def.phases:
                    logger.info(
                        "[FlowModifier] Phase '%s' not found for append modifier '%s'. "
                        "Falling back to last phase '%s'.",
                        modifier.phase, modifier.modifier_id, flow_def.phases[-1],
                    )
                    modifier = copy.copy(modifier)
                    modifier.phase = flow_def.phases[-1]
                else:
                    result = ModifierApplyResult(
                        success=False,
                        modifier_id=modifier.modifier_id,
                        action=modifier.action,
                        target_flow_id=modifier.target_flow_id,
                        target_step_id=modifier.target_step_id,
                        skipped_reason=f"phase_not_found: {modifier.phase}"
                    )
                    self._log_modifier_skip(modifier, result.skipped_reason)
                    results.append(result)
                    continue

            if modifier.action == "inject_before":
                target = modifier.target_step_id or ""
                if target not in inject_before_groups:
                    inject_before_groups[target] = []
                inject_before_groups[target].append(modifier)
            elif modifier.action == "inject_after":
                target = modifier.target_step_id or ""
                if target not in inject_after_groups:
                    inject_after_groups[target] = []
                inject_after_groups[target].append(modifier)
            elif modifier.action == "append":
                phase = modifier.phase
                if phase not in append_groups:
                    append_groups[phase] = []
                append_groups[phase].append(modifier)
            else:
                # replace, remove は個別処理
                other_modifiers.append(modifier)

        # 各グループ内でソート: priority → step.id → modifier_id
        for key in inject_before_groups:
            inject_before_groups[key] = sorted(
                inject_before_groups[key],
                key=lambda m: (m.priority, m.step.get("id", "") if m.step else "", m.modifier_id)
            )
        for key in inject_after_groups:
            inject_after_groups[key] = sorted(
                inject_after_groups[key],
                key=lambda m: (m.priority, m.step.get("id", "") if m.step else "", m.modifier_id)
            )
        for key in append_groups:
            append_groups[key] = sorted(
                append_groups[key],
                key=lambda m: (m.priority, m.step.get("id", "") if m.step else "", m.modifier_id)
            )

        # Wave 9: 衝突検出（警告のみ、動作は変更しない）
        self._detect_conflicts(modifiers, results)

        # 1. replace, removeを先に適用
        for modifier in other_modifiers:
            result = self._apply_single_modifier(new_steps, modifier, flow_def.phases)
            results.append(result)

        # 2. inject_before を一括適用（同一注入点ごと）
        for target_step_id, group in inject_before_groups.items():
            # #7: 特殊 target_step_id 値の解決
            if target_step_id == "__first__":
                target_index = 0 if new_steps else -1
            elif target_step_id == "__last__":
                target_index = (len(new_steps) - 1) if new_steps else -1
            else:
                target_index = self._find_step_index(new_steps, target_step_id)
            if target_index < 0:
                # target不在：全てスキップ
                for modifier in group:
                    result = ModifierApplyResult(
                        success=False,
                        modifier_id=modifier.modifier_id,
                        action=modifier.action,
                        target_flow_id=modifier.target_flow_id,
                        target_step_id=modifier.target_step_id,
                        skipped_reason=f"target_step_not_found: {target_step_id}"
                    )
                    self._log_modifier_skip(modifier, result.skipped_reason)
                    results.append(result)
                continue

            # 同一注入点のステップを順番に作成し、一括挿入
            for i, modifier in enumerate(group):
                new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
                new_steps.insert(target_index + i, new_step)
                result = ModifierApplyResult(
                    success=True,
                    modifier_id=modifier.modifier_id,
                    action=modifier.action,
                    target_flow_id=modifier.target_flow_id,
                    target_step_id=modifier.target_step_id
                )
                results.append(result)
                self._log_modifier_success(modifier)

        # 3. inject_after を一括適用（同一注入点ごと）
        for target_step_id, group in inject_after_groups.items():
            # #7: 特殊 target_step_id 値の解決
            if target_step_id == "__first__":
                target_index = 0 if new_steps else -1
            elif target_step_id == "__last__":
                target_index = (len(new_steps) - 1) if new_steps else -1
            else:
                target_index = self._find_step_index(new_steps, target_step_id)
            if target_index < 0:
                for modifier in group:
                    result = ModifierApplyResult(
                        success=False,
                        modifier_id=modifier.modifier_id,
                        action=modifier.action,
                        target_flow_id=modifier.target_flow_id,
                        target_step_id=modifier.target_step_id,
                        skipped_reason=f"target_step_not_found: {target_step_id}"
                    )
                    self._log_modifier_skip(modifier, result.skipped_reason)
                    results.append(result)
                continue

            # target_index + 1 の位置から一括挿入
            insert_pos = target_index + 1
            for i, modifier in enumerate(group):
                new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
                new_steps.insert(insert_pos + i, new_step)
                result = ModifierApplyResult(
                    success=True,
                    modifier_id=modifier.modifier_id,
                    action=modifier.action,
                    target_flow_id=modifier.target_flow_id,
                    target_step_id=modifier.target_step_id
                )
                results.append(result)
                self._log_modifier_success(modifier)

        # 4. append を適用
        for phase, group in append_groups.items():
            for modifier in group:
                self._action_append(new_steps, modifier, flow_def.phases)
                result = ModifierApplyResult(
                    success=True,
                    modifier_id=modifier.modifier_id,
                    action=modifier.action,
                    target_flow_id=modifier.target_flow_id,
                    target_step_id=modifier.target_step_id
                )
                results.append(result)
                self._log_modifier_success(modifier)

        # 新しいFlowDefinitionを作成（再ソートしない）
        new_flow_def = FlowDefinition(
            flow_id=flow_def.flow_id,
            inputs=copy.deepcopy(flow_def.inputs),
            outputs=copy.deepcopy(flow_def.outputs),
            phases=list(flow_def.phases),
            defaults=copy.deepcopy(flow_def.defaults),
            steps=new_steps,
            source_file=flow_def.source_file,
            source_type=flow_def.source_type,
            source_pack_id=flow_def.source_pack_id
        )

        # #40: dry_run モードでは元の FlowDefinition を返す
        if self._dry_run:
            return flow_def, results

        return new_flow_def, results

    def _apply_single_modifier(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> ModifierApplyResult:
        """単一のmodifierを適用（replace, remove用）"""
        result = ModifierApplyResult(
            success=False,
            modifier_id=modifier.modifier_id,
            action=modifier.action,
            target_flow_id=modifier.target_flow_id,
            target_step_id=modifier.target_step_id
        )

        try:
            if modifier.action == "replace":
                success = self._action_replace(steps, modifier, phases)
                if not success:
                    result.skipped_reason = f"target_step_not_found: {modifier.target_step_id}"
                    self._log_modifier_skip(modifier, result.skipped_reason)
                    return result
            elif modifier.action == "remove":
                success = self._action_remove(steps, modifier)
                if not success:
                    result.skipped_reason = f"target_step_not_found: {modifier.target_step_id}"
                    self._log_modifier_skip(modifier, result.skipped_reason)
                    return result
            else:
                result.errors.append(f"Unknown action: {modifier.action}")
                return result

            result.success = True
            self._log_modifier_success(modifier)
        except Exception as e:
            result.errors.append(str(e))

        return result

    def _log_modifier_skip(self, modifier: FlowModifierDef, reason: str) -> None:
        """modifierスキップをログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_modifier_application(
                modifier_id=modifier.modifier_id,
                target_flow_id=modifier.target_flow_id,
                action=modifier.action,
                success=False,
                target_step_id=modifier.target_step_id,
                skipped_reason=reason,
                error=None
            )
        except Exception:
            pass

    def _log_modifier_success(self, modifier: FlowModifierDef) -> None:
        """modifier成功をログに記録（警告付き）"""
        # 明示的な警告ログ出力
        step_id = modifier.step.get("id", "unknown") if modifier.step else "N/A"
        logger.warning(
            "[FlowModifier] WARNING: Pack '%s' is modifying flow '%s': "
            "- %s step '%s': %s",
            modifier.source_pack_id or "unknown",
            modifier.target_flow_id,
            modifier.action,
            modifier.target_step_id or "N/A",
            step_id,
        )

        # 無条件適用（requires が空）の場合は追加警告
        if not modifier.requires.interfaces and not modifier.requires.capabilities:
            logger.warning(
                "[FlowModifier] NOTICE: Modifier '%s' from pack '%s' has no "
                "'requires' conditions - it applies unconditionally to flow '%s'. "
                "Consider adding 'requires' to limit scope.",
                modifier.modifier_id,
                modifier.source_pack_id or "unknown",
                modifier.target_flow_id,
            )

        # 監査ログにも記録
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_modifier_application(
                modifier_id=modifier.modifier_id,
                target_flow_id=modifier.target_flow_id,
                action=modifier.action,
                success=True,
                target_step_id=modifier.target_step_id,
                skipped_reason=None,
                error=None
            )
        except Exception:
            pass

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
            timeout_seconds=step_dict.get("timeout_seconds", 60.0),
            principal_id=step_dict.get("principal_id"),
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

    def _action_replace(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef,
        phases: List[str]
    ) -> bool:
        """replace: target_step_idのステップを置換"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            return False

        new_step = self._step_from_dict(modifier.step, modifier.phase, modifier.modifier_id)
        steps[target_index] = new_step
        return True

    def _action_remove(
        self,
        steps: List[FlowStep],
        modifier: FlowModifierDef
    ) -> bool:
        """remove: target_step_idのステップを削除"""
        target_index = self._find_step_index(steps, modifier.target_step_id)
        if target_index < 0:
            return False

        steps.pop(target_index)
        return True

    def dry_run_report(
        self,
        flow_def: FlowDefinition,
        modifiers: List[FlowModifierDef],
    ) -> Dict[str, Any]:
        """
        dry-run: 実際の変更を行わず、適用されるはずの変更を記録して返す。

        API 経由で呼び出す想定。内部的に dry_run=True の Applier を使う。

        Args:
            flow_def: 元の FlowDefinition
            modifiers: 適用する modifier リスト

        Returns:
            {"dry_run": True, "flow_id": str, "changes": [...]}
        """
        # 一時的に dry_run を有効化
        orig = self._dry_run
        self._dry_run = True
        try:
            _, results = self.apply_modifiers(flow_def, modifiers)
        finally:
            self._dry_run = orig

        changes = []
        for r in results:
            changes.append({
                "modifier_id": r.modifier_id,
                "action": r.action,
                "target_flow_id": r.target_flow_id,
                "target_step_id": r.target_step_id,
                "success": r.success,
                "skipped_reason": r.skipped_reason,
                "errors": r.errors,
            })

        return {
            "dry_run": True,
            "flow_id": flow_def.flow_id,
            "total_modifiers": len(modifiers),
            "applied": sum(1 for c in changes if c["success"]),
            "skipped": sum(1 for c in changes if not c["success"]),
            "changes": changes,
        }


# グローバル変数（後方互換のため残存。DI コンテナ優先）
_global_modifier_loader: Optional[FlowModifierLoader] = None
_global_modifier_applier: Optional[FlowModifierApplier] = None
_modifier_lock = threading.Lock()


def get_modifier_loader() -> FlowModifierLoader:
    """
    グローバルな FlowModifierLoader を取得する。

    DI コンテナ経由で遅延初期化・キャッシュされる。

    Returns:
        FlowModifierLoader インスタンス
    """
    from .di_container import get_container
    return get_container().get("modifier_loader")


def get_modifier_applier() -> FlowModifierApplier:
    """
    グローバルな FlowModifierApplier を取得する。

    DI コンテナ経由で遅延初期化・キャッシュされる。

    Returns:
        FlowModifierApplier インスタンス
    """
    from .di_container import get_container
    return get_container().get("modifier_applier")


def reset_modifier_loader() -> FlowModifierLoader:
    """
    FlowModifierLoader をリセットする（テスト用）。

    新しいインスタンスを生成し、DI コンテナのキャッシュを置き換える。

    Returns:
        新しい FlowModifierLoader インスタンス
    """
    global _global_modifier_loader
    with _modifier_lock:
        _global_modifier_loader = FlowModifierLoader()
    # DI コンテナのキャッシュも更新（_modifier_lock の外で実行してデッドロック回避）
    from .di_container import get_container
    get_container().set_instance("modifier_loader", _global_modifier_loader)
    return _global_modifier_loader


def reset_modifier_applier() -> FlowModifierApplier:
    """
    FlowModifierApplier をリセットする（テスト用）。

    新しいインスタンスを生成し、DI コンテナのキャッシュを置き換える。

    Returns:
        新しい FlowModifierApplier インスタンス
    """
    global _global_modifier_applier
    with _modifier_lock:
        _global_modifier_applier = FlowModifierApplier()
    # DI コンテナのキャッシュも更新（_modifier_lock の外で実行してデッドロック回避）
    from .di_container import get_container
    get_container().set_instance("modifier_applier", _global_modifier_applier)
    return _global_modifier_applier
