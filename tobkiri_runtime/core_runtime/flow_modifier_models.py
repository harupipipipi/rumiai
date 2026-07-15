"""
flow_modifier_models.py - FlowModifier 用データモデル

Wave 13 T-048: flow_modifier.py から分割。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


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
