"""
flow_loader.py - Flow定義ファイルのローダー

flows/(公式)と ecosystem/flows/(エコシステム)からYAMLファイルを読み込み、
InterfaceRegistryに登録する。

設計原則:
- Flowはファイルからロードされる(setup.py登録に依存しない)
- 公式は具体的なドメイン概念を持たない
- phases/priority/idによる決定的な実行順序
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class FlowStep:
    """Flowステップの正規化表現"""
    id: str
    phase: str
    priority: int
    type: str
    when: Optional[str]
    input: Any
    output: Optional[str]
    raw: Dict[str, Any]
    
    # python_file_call用
    owner_pack: Optional[str] = None
    file: Optional[str] = None
    timeout_seconds: float = 60.0


@dataclass
class FlowDefinition:
    """Flow定義の正規化表現"""
    flow_id: str
    inputs: Dict[str, str]
    outputs: Dict[str, str]
    phases: List[str]
    defaults: Dict[str, Any]
    steps: List[FlowStep]
    source_file: Optional[Path] = None
    source_type: str = "unknown"  # "official" or "ecosystem"
    
    def to_dict(self) -> Dict[str, Any]:
        """既存Kernelが処理できる形式に変換"""
        return {
            "flow_id": self.flow_id,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "phases": self.phases,
            "defaults": self.defaults,
            "steps": [self._step_to_dict(s) for s in self.steps],
            "_source_file": str(self.source_file) if self.source_file else None,
            "_source_type": self.source_type,
        }
    
    def _step_to_dict(self, step: FlowStep) -> Dict[str, Any]:
        """ステップを辞書形式に変換"""
        d = {
            "id": step.id,
            "phase": step.phase,
            "priority": step.priority,
            "type": step.type,
        }
        if step.when:
            d["when"] = step.when
        if step.input is not None:
            d["input"] = step.input
        if step.output:
            d["output"] = step.output
        if step.owner_pack:
            d["owner_pack"] = step.owner_pack
        if step.file:
            d["file"] = step.file
        if step.timeout_seconds != 60.0:
            d["timeout_seconds"] = step.timeout_seconds
        return d


@dataclass
class FlowLoadResult:
    """Flowロード結果"""
    success: bool
    flow_id: Optional[str] = None
    flow_def: Optional[FlowDefinition] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class FlowLoader:
    """
    Flowファイルローダー
    
    flows/(公式)と ecosystem/flows/(エコシステム)から
    YAMLファイルを読み込み、正規化する。
    """
    
    OFFICIAL_FLOWS_DIR = "flows"
    ECOSYSTEM_FLOWS_DIR = "ecosystem/flows"
    
    def __init__(self):
        self._lock = threading.RLock()
        self._loaded_flows: Dict[str, FlowDefinition] = {}
        self._load_errors: List[Dict[str, Any]] = []
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def load_all_flows(self) -> Dict[str, FlowDefinition]:
        """
        全Flowファイルをロード
        
        Returns:
            flow_id -> FlowDefinition のマップ
        """
        with self._lock:
            self._loaded_flows.clear()
            self._load_errors.clear()
            
            # 1. 公式Flowをロード
            official_dir = Path(self.OFFICIAL_FLOWS_DIR)
            if official_dir.exists():
                self._load_directory(official_dir, "official")
            
            # 2. エコシステムFlowをロード
            ecosystem_dir = Path(self.ECOSYSTEM_FLOWS_DIR)
            if ecosystem_dir.exists():
                self._load_directory(ecosystem_dir, "ecosystem")
            
            return dict(self._loaded_flows)
    
    def _load_directory(self, directory: Path, source_type: str) -> None:
        """ディレクトリ内のFlowファイルをロード"""
        for yaml_file in sorted(directory.glob("*.flow.yaml")):
            result = self.load_flow_file(yaml_file, source_type)
            
            if result.success and result.flow_def:
                # 重複チェック
                if result.flow_id in self._loaded_flows:
                    existing = self._loaded_flows[result.flow_id]
                    # エコシステムが公式を上書きするのは許可しない
                    if existing.source_type == "official" and source_type == "ecosystem":
                        self._load_errors.append({
                            "file": str(yaml_file),
                            "error": f"Cannot override official flow '{result.flow_id}' from ecosystem",
                            "ts": self._now_ts()
                        })
                        continue
                
                self._loaded_flows[result.flow_id] = result.flow_def
            else:
                self._load_errors.append({
                    "file": str(yaml_file),
                    "errors": result.errors,
                    "ts": self._now_ts()
                })
    
    def load_flow_file(self, file_path: Path, source_type: str = "unknown") -> FlowLoadResult:
        """
        単一のFlowファイルをロード
        
        Args:
            file_path: YAMLファイルのパス
            source_type: "official" or "ecosystem"
        
        Returns:
            FlowLoadResult
        """
        result = FlowLoadResult(success=False)
        
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
            result.errors.append("Flow file must be a YAML object")
            return result
        
        # 必須フィールドチェック
        flow_id = raw_data.get("flow_id")
        if not flow_id or not isinstance(flow_id, str):
            result.errors.append("Missing or invalid 'flow_id'")
            return result
        
        result.flow_id = flow_id
        
        # inputs/outputs(任意だがあれば型チェック)
        inputs = raw_data.get("inputs", {})
        if not isinstance(inputs, dict):
            result.errors.append("'inputs' must be an object")
            return result
        
        outputs = raw_data.get("outputs", {})
        if not isinstance(outputs, dict):
            result.errors.append("'outputs' must be an object")
            return result
        
        # phases(必須)
        phases = raw_data.get("phases", [])
        if not isinstance(phases, list) or not phases:
            result.errors.append("'phases' must be a non-empty array")
            return result
        
        for i, phase in enumerate(phases):
            if not isinstance(phase, str):
                result.errors.append(f"phases[{i}] must be a string")
                return result
        
        # defaults(任意)
        defaults = raw_data.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
        
        defaults.setdefault("fail_soft", True)
        defaults.setdefault("on_missing_step", "skip")
        
        # steps(必須)
        raw_steps = raw_data.get("steps", [])
        if not isinstance(raw_steps, list):
            result.errors.append("'steps' must be an array")
            return result
        
        # ステップをパース
        steps, step_errors, step_warnings = self._parse_steps(raw_steps, phases, file_path)
        result.errors.extend(step_errors)
        result.warnings.extend(step_warnings)
        
        if result.errors:
            return result
        
        # ステップをソート(phase順 → priority順 → id順)
        sorted_steps = self._sort_steps(steps, phases)
        
        # FlowDefinitionを作成
        flow_def = FlowDefinition(
            flow_id=flow_id,
            inputs=inputs,
            outputs=outputs,
            phases=phases,
            defaults=defaults,
            steps=sorted_steps,
            source_file=file_path,
            source_type=source_type
        )
        
        result.success = True
        result.flow_def = flow_def
        return result
    
    def _parse_steps(
        self,
        raw_steps: List[Any],
        phases: List[str],
        file_path: Path
    ) -> Tuple[List[FlowStep], List[str], List[str]]:
        """ステップをパースして正規化"""
        steps = []
        errors = []
        warnings = []
        seen_ids = set()
        
        for i, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                errors.append(f"steps[{i}] must be an object")
                continue
            
            # id(必須)
            step_id = raw_step.get("id")
            if not step_id or not isinstance(step_id, str):
                errors.append(f"steps[{i}]: missing or invalid 'id'")
                continue
            
            if step_id in seen_ids:
                errors.append(f"steps[{i}]: duplicate id '{step_id}'")
                continue
            seen_ids.add(step_id)
            
            # phase(必須)
            phase = raw_step.get("phase")
            if not phase or not isinstance(phase, str):
                errors.append(f"steps[{i}] ({step_id}): missing or invalid 'phase'")
                continue
            
            if phase not in phases:
                errors.append(f"steps[{i}] ({step_id}): phase '{phase}' not in phases list")
                continue
            
            # type(必須)
            step_type = raw_step.get("type")
            if not step_type or not isinstance(step_type, str):
                errors.append(f"steps[{i}] ({step_id}): missing or invalid 'type'")
                continue
            
            # priority(任意、デフォルト100)
            priority = raw_step.get("priority", 100)
            if not isinstance(priority, (int, float)):
                warnings.append(f"steps[{i}] ({step_id}): invalid priority, using 100")
                priority = 100
            priority = int(priority)
            
            # when(任意)
            when = raw_step.get("when")
            if when is not None and not isinstance(when, str):
                warnings.append(f"steps[{i}] ({step_id}): 'when' must be a string")
                when = None
            
            # input(任意)
            step_input = raw_step.get("input")
            
            # output(任意)
            output = raw_step.get("output")
            if output is not None and not isinstance(output, str):
                warnings.append(f"steps[{i}] ({step_id}): 'output' must be a string")
                output = None
            
            # FlowStepを作成
            step = FlowStep(
                id=step_id,
                phase=phase,
                priority=priority,
                type=step_type,
                when=when,
                input=step_input,
                output=output,
                raw=raw_step
            )
            
            # python_file_call固有のフィールド
            if step_type == "python_file_call":
                step.owner_pack = raw_step.get("owner_pack")
                step.file = raw_step.get("file")
                step.timeout_seconds = raw_step.get("timeout_seconds", 60.0)
                
                if not step.file:
                    errors.append(f"steps[{i}] ({step_id}): python_file_call requires 'file'")
                    continue
            
            steps.append(step)
        
        return steps, errors, warnings
    
    def _sort_steps(self, steps: List[FlowStep], phases: List[str]) -> List[FlowStep]:
        """
        ステップを決定的にソート
        
        ソート順:
        1. phase(phasesリストでの順序)
        2. priority(昇順、小さいほど先)
        3. id(アルファベット順、タイブレーク)
        """
        phase_order = {phase: i for i, phase in enumerate(phases)}
        
        return sorted(
            steps,
            key=lambda s: (phase_order.get(s.phase, 999), s.priority, s.id)
        )
    
    def get_loaded_flows(self) -> Dict[str, FlowDefinition]:
        """ロード済みFlowを取得"""
        with self._lock:
            return dict(self._loaded_flows)
    
    def get_load_errors(self) -> List[Dict[str, Any]]:
        """ロードエラーを取得"""
        with self._lock:
            return list(self._load_errors)
    
    def get_flow(self, flow_id: str) -> Optional[FlowDefinition]:
        """特定のFlowを取得"""
        with self._lock:
            return self._loaded_flows.get(flow_id)


# グローバルインスタンス
_global_flow_loader: Optional[FlowLoader] = None
_loader_lock = threading.Lock()


def get_flow_loader() -> FlowLoader:
    """グローバルなFlowLoaderを取得"""
    global _global_flow_loader
    if _global_flow_loader is None:
        with _loader_lock:
            if _global_flow_loader is None:
                _global_flow_loader = FlowLoader()
    return _global_flow_loader


def reset_flow_loader() -> FlowLoader:
    """FlowLoaderをリセット(テスト用)"""
    global _global_flow_loader
    with _loader_lock:
        _global_flow_loader = FlowLoader()
    return _global_flow_loader


def load_all_flows() -> Dict[str, FlowDefinition]:
    """全Flowをロード(ショートカット)"""
    return get_flow_loader().load_all_flows()
