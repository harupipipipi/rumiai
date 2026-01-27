import os
from pathlib import Path

# プロジェクトルートを設定（このスクリプトの実行場所に応じて調整）
PROJECT_ROOT = Path(".")

def write_file(path: str, content: str):
    """ファイルを書き込む（ディレクトリがなければ作成）"""
    full_path = PROJECT_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ 作成/更新: {path}")

# =============================================================================
# 1. 新規ファイル: core_runtime/function_alias.py
# =============================================================================

function_alias_py = '''"""
function_alias.py - 関数エイリアス（同義語マッピング）システム

異なる名前で同じ概念を指せるようにし、互換性を高める。

設計原則:
- 公式は具体的なエイリアスをハードコードしない
- ecosystemが自由にエイリアスを追加可能
- 正規名（canonical）と複数のエイリアスをマッピング

Usage:
    alias = get_function_alias_registry()
    
    # エイリアスを登録（ecosystem側で実行）
    alias.register_aliases("ai", ["ai_client", "ai_provider", "llm"])
    alias.register_aliases("tool", ["tools", "function_calling", "tooluse"])
    
    # 解決
    alias.resolve("ai_provider")  # → "ai"
    alias.resolve("unknown")       # → "unknown"（未登録はそのまま）
    
    # 正規名に対応する全ての名前を取得
    alias.find_all("ai")  # → ["ai", "ai_client", "ai_provider", "llm"]
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class FunctionAliasRegistry:
    """
    関数エイリアスレジストリ
    
    正規名（canonical）とエイリアスのマッピングを管理する。
    スレッドセーフ。
    """
    
    # canonical -> set of aliases (canonical自身を含む)
    _canonical_to_aliases: Dict[str, Set[str]] = field(default_factory=dict)
    
    # alias -> canonical
    _alias_to_canonical: Dict[str, str] = field(default_factory=dict)
    
    _lock: threading.RLock = field(default_factory=threading.RLock)
    
    def register_aliases(self, canonical: str, aliases: List[str]) -> None:
        """
        正規名とエイリアスを登録
        
        Args:
            canonical: 正規名（例: "ai", "tool"）
            aliases: エイリアスのリスト（例: ["ai_client", "ai_provider"]）
        
        Note:
            - canonical自身も自動的にエイリアスとして登録される
            - 既に他のcanonicalに登録されているaliasは上書きされる
        """
        with self._lock:
            # canonicalが既存のaliasとして登録されている場合、それを解除
            if canonical in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[canonical]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(canonical)
            
            # canonical自身を含むセットを作成/更新
            if canonical not in self._canonical_to_aliases:
                self._canonical_to_aliases[canonical] = {canonical}
            
            # aliasを登録
            for alias in aliases:
                # 既存の登録を解除
                if alias in self._alias_to_canonical:
                    old_canonical = self._alias_to_canonical[alias]
                    if old_canonical != canonical:
                        self._canonical_to_aliases[old_canonical].discard(alias)
                
                self._canonical_to_aliases[canonical].add(alias)
                self._alias_to_canonical[alias] = canonical
            
            # canonical自身も登録
            self._alias_to_canonical[canonical] = canonical
    
    def add_alias(self, canonical: str, alias: str) -> bool:
        """
        単一のエイリアスを追加
        
        Args:
            canonical: 正規名
            alias: 追加するエイリアス
        
        Returns:
            成功した場合True
        """
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                # canonicalが未登録の場合は新規作成
                self._canonical_to_aliases[canonical] = {canonical}
                self._alias_to_canonical[canonical] = canonical
            
            # 既存の登録を解除
            if alias in self._alias_to_canonical:
                old_canonical = self._alias_to_canonical[alias]
                if old_canonical != canonical:
                    self._canonical_to_aliases[old_canonical].discard(alias)
            
            self._canonical_to_aliases[canonical].add(alias)
            self._alias_to_canonical[alias] = canonical
            return True
    
    def resolve(self, name: str) -> str:
        """
        名前を正規名に解決
        
        Args:
            name: 解決する名前
        
        Returns:
            正規名。未登録の場合はnameをそのまま返す。
        """
        with self._lock:
            return self._alias_to_canonical.get(name, name)
    
    def find_all(self, canonical: str) -> List[str]:
        """
        正規名に対応する全ての名前（エイリアス）を取得
        
        Args:
            canonical: 正規名
        
        Returns:
            canonical自身を含む全てのエイリアスのリスト。
            未登録の場合は[canonical]を返す。
        """
        with self._lock:
            if canonical in self._canonical_to_aliases:
                return sorted(list(self._canonical_to_aliases[canonical]))
            return [canonical]
    
    def is_alias_of(self, name: str, canonical: str) -> bool:
        """
        nameがcanonicalのエイリアスかどうか判定
        
        Args:
            name: 判定する名前
            canonical: 正規名
        
        Returns:
            エイリアスの場合True
        """
        with self._lock:
            resolved = self._alias_to_canonical.get(name)
            return resolved == canonical
    
    def get_canonical(self, name: str) -> Optional[str]:
        """
        名前の正規名を取得（未登録ならNone）
        
        Args:
            name: 名前
        
        Returns:
            正規名、または未登録ならNone
        """
        with self._lock:
            return self._alias_to_canonical.get(name)
    
    def list_all_canonicals(self) -> List[str]:
        """全ての正規名を取得"""
        with self._lock:
            return sorted(list(self._canonical_to_aliases.keys()))
    
    def list_all_mappings(self) -> Dict[str, List[str]]:
        """全てのマッピングを取得"""
        with self._lock:
            return {
                canonical: sorted(list(aliases))
                for canonical, aliases in self._canonical_to_aliases.items()
            }
    
    def remove_alias(self, alias: str) -> bool:
        """
        エイリアスを削除
        
        Args:
            alias: 削除するエイリアス
        
        Returns:
            削除成功した場合True
        
        Note:
            正規名自身は削除できない
        """
        with self._lock:
            if alias not in self._alias_to_canonical:
                return False
            
            canonical = self._alias_to_canonical[alias]
            
            # 正規名自身は削除しない
            if alias == canonical:
                return False
            
            del self._alias_to_canonical[alias]
            self._canonical_to_aliases[canonical].discard(alias)
            return True
    
    def remove_canonical(self, canonical: str) -> bool:
        """
        正規名とその全てのエイリアスを削除
        
        Args:
            canonical: 削除する正規名
        
        Returns:
            削除成功した場合True
        """
        with self._lock:
            if canonical not in self._canonical_to_aliases:
                return False
            
            # 関連する全てのエイリアスを削除
            for alias in list(self._canonical_to_aliases[canonical]):
                if alias in self._alias_to_canonical:
                    del self._alias_to_canonical[alias]
            
            del self._canonical_to_aliases[canonical]
            return True
    
    def clear(self) -> None:
        """全てのマッピングをクリア"""
        with self._lock:
            self._canonical_to_aliases.clear()
            self._alias_to_canonical.clear()


# グローバルインスタンス
_global_function_alias_registry: Optional[FunctionAliasRegistry] = None
_registry_lock = threading.Lock()


def get_function_alias_registry() -> FunctionAliasRegistry:
    """グローバルなFunctionAliasRegistryインスタンスを取得"""
    global _global_function_alias_registry
    if _global_function_alias_registry is None:
        with _registry_lock:
            if _global_function_alias_registry is None:
                _global_function_alias_registry = FunctionAliasRegistry()
    return _global_function_alias_registry


def reset_function_alias_registry() -> FunctionAliasRegistry:
    """FunctionAliasRegistryをリセット（テスト用）"""
    global _global_function_alias_registry
    with _registry_lock:
        _global_function_alias_registry = FunctionAliasRegistry()
    return _global_function_alias_registry
'''

write_file("core_runtime/function_alias.py", function_alias_py)

# =============================================================================
# 2. 新規ファイル: core_runtime/flow_composer.py
# =============================================================================

flow_composer_py = '''"""
flow_composer.py - Flow合成・修正システム

ecosystemコンポーネントがFlowを動的に修正するための基盤。

設計原則:
- 公式は修正の「仕組み」のみ提供
- 具体的な修正ロジックはecosystem側で定義
- 安全性を考慮（不正な修正を検出）

Usage:
    composer = get_flow_composer()
    
    # modifierを収集
    modifiers = composer.collect_modifiers(interface_registry)
    
    # Flowに修正を適用
    modified_flow = composer.apply_modifiers(flow_def, modifiers)
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable

from .function_alias import FunctionAliasRegistry, get_function_alias_registry


@dataclass
class FlowModifier:
    """Flow修正の定義"""
    id: str
    priority: int
    target_flow: Optional[str]  # 対象Flow名（Noneなら全Flow）
    requires: Dict[str, Any]    # 適用条件
    modifications: List[Dict[str, Any]]  # 修正操作のリスト
    source_component: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "priority": self.priority,
            "target_flow": self.target_flow,
            "requires": self.requires,
            "modifications": self.modifications,
            "source_component": self.source_component
        }


class FlowComposer:
    """
    Flow合成・修正システム
    
    ecosystemコンポーネントが登録したflow.modifierを収集し、
    Flow定義に適用する。
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._applied_modifiers: List[Dict[str, Any]] = []
        self._alias_registry: Optional[FunctionAliasRegistry] = None
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def set_alias_registry(self, registry: FunctionAliasRegistry) -> None:
        """エイリアスレジストリを設定"""
        self._alias_registry = registry
    
    def collect_modifiers(self, interface_registry) -> List[FlowModifier]:
        """
        InterfaceRegistryからflow.modifierを収集
        
        Args:
            interface_registry: InterfaceRegistry インスタンス
        
        Returns:
            優先度順にソートされたFlowModifierのリスト
        """
        raw_modifiers = interface_registry.get("flow.modifier", strategy="all") or []
        
        modifiers = []
        for raw in raw_modifiers:
            if not isinstance(raw, dict):
                continue
            
            try:
                modifier = FlowModifier(
                    id=raw.get("id", f"modifier_{len(modifiers)}"),
                    priority=raw.get("priority", 100),
                    target_flow=raw.get("target_flow"),
                    requires=raw.get("requires", {}),
                    modifications=raw.get("modifications", []),
                    source_component=raw.get("source_component")
                )
                modifiers.append(modifier)
            except Exception:
                continue
        
        # 優先度でソート（小さい方が先）
        modifiers.sort(key=lambda m: m.priority)
        return modifiers
    
    def check_requirements(
        self,
        modifier: FlowModifier,
        interface_registry,
        available_capabilities: Dict[str, Any] = None
    ) -> bool:
        """
        修正の適用条件をチェック
        
        Args:
            modifier: チェックするmodifier
            interface_registry: InterfaceRegistry インスタンス
            available_capabilities: 利用可能なcapabilitiesの辞書
        
        Returns:
            条件を満たす場合True
        """
        requires = modifier.requires
        
        if not requires:
            return True
        
        # capabilities チェック
        required_caps = requires.get("capabilities", [])
        if required_caps:
            if available_capabilities is None:
                return False
            for cap in required_caps:
                if not available_capabilities.get(cap):
                    return False
        
        # modifiers チェック（他のmodifierが適用済みであること）
        required_mods = requires.get("modifiers", [])
        if required_mods:
            applied_ids = {m.get("id") for m in self._applied_modifiers}
            for mod_id in required_mods:
                if mod_id not in applied_ids:
                    return False
        
        # interfaces チェック（特定のIRキーが登録されていること）
        required_interfaces = requires.get("interfaces", [])
        if required_interfaces:
            for iface in required_interfaces:
                if interface_registry.get(iface) is None:
                    return False
        
        return True
    
    def apply_modifiers(
        self,
        flow_def: Dict[str, Any],
        modifiers: List[FlowModifier],
        interface_registry = None,
        available_capabilities: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Flow定義に修正を適用
        
        Args:
            flow_def: 元のFlow定義
            modifiers: 適用するmodifierのリスト
            interface_registry: InterfaceRegistry インスタンス（条件チェック用）
            available_capabilities: 利用可能なcapabilities
        
        Returns:
            修正後のFlow定義（新しい辞書、元は変更しない）
        """
        result = copy.deepcopy(flow_def)
        
        with self._lock:
            self._applied_modifiers.clear()
            
            for modifier in modifiers:
                # 条件チェック
                if interface_registry and not self.check_requirements(
                    modifier, interface_registry, available_capabilities
                ):
                    continue
                
                # 修正を適用
                try:
                    result = self._apply_single_modifier(result, modifier)
                    self._applied_modifiers.append({
                        "id": modifier.id,
                        "applied_at": self._now_ts(),
                        "source_component": modifier.source_component
                    })
                except Exception as e:
                    # 適用失敗は記録して継続
                    print(f"[FlowComposer] Modifier '{modifier.id}' failed: {e}")
                    continue
        
        return result
    
    def _apply_single_modifier(
        self,
        flow_def: Dict[str, Any],
        modifier: FlowModifier
    ) -> Dict[str, Any]:
        """
        単一の修正を適用
        
        サポートする操作:
        - inject_before: 指定ステップの前にステップを挿入
        - inject_after: 指定ステップの後にステップを挿入
        - replace: 指定ステップを置換
        - wrap_with_loop: 指定ステップ群をループで囲む
        - remove: 指定ステップを削除
        - set_property: ステップのプロパティを設定
        """
        for modification in modifier.modifications:
            action = modification.get("action")
            
            if action == "inject_before":
                flow_def = self._action_inject(
                    flow_def, modification, "before"
                )
            elif action == "inject_after":
                flow_def = self._action_inject(
                    flow_def, modification, "after"
                )
            elif action == "replace":
                flow_def = self._action_replace(flow_def, modification)
            elif action == "wrap_with_loop":
                flow_def = self._action_wrap_loop(flow_def, modification)
            elif action == "remove":
                flow_def = self._action_remove(flow_def, modification)
            elif action == "set_property":
                flow_def = self._action_set_property(flow_def, modification)
            # 未知の操作は無視
        
        return flow_def
    
    def _find_step_index(
        self,
        steps: List[Dict[str, Any]],
        target: Dict[str, Any]
    ) -> int:
        """
        ターゲットに一致するステップのインデックスを検索
        
        target形式:
        - {"id": "step_id"}: IDで検索
        - {"function": "ai"}: 関数名（エイリアス解決あり）で検索
        - {"handler": "ai.generate"}: ハンドラ名で検索
        """
        alias_registry = self._alias_registry or get_function_alias_registry()
        
        for i, step in enumerate(steps):
            # ID検索
            if "id" in target:
                if step.get("id") == target["id"]:
                    return i
            
            # 関数名検索（エイリアス解決）
            if "function" in target:
                target_function = target["function"]
                target_aliases = alias_registry.find_all(target_function)
                
                step_handler = step.get("handler", "")
                step_function = step_handler.split(".")[0] if step_handler else ""
                step_type = step.get("type", "")
                
                # runブロック内のhandlerもチェック
                run_block = step.get("run", {})
                if isinstance(run_block, dict):
                    run_handler = run_block.get("handler", "")
                    run_function = run_handler.split(".")[0] if run_handler else ""
                    if run_function in target_aliases:
                        return i
                
                # ハンドラの先頭部分またはtypeがエイリアスに一致するか
                if step_function in target_aliases or step_type in target_aliases:
                    return i
            
            # ハンドラ名検索
            if "handler" in target:
                if step.get("handler") == target["handler"]:
                    return i
                # runブロック内もチェック
                run_block = step.get("run", {})
                if isinstance(run_block, dict):
                    if run_block.get("handler") == target["handler"]:
                        return i
        
        return -1
    
    def _action_inject(
        self,
        flow_def: Dict[str, Any],
        modification: Dict[str, Any],
        position: str  # "before" or "after"
    ) -> Dict[str, Any]:
        """inject_before / inject_after の実装"""
        target_step = modification.get("target_step", {})
        new_steps = modification.get("steps", [])
        target_pipeline = modification.get("pipeline")
        
        if not new_steps:
            return flow_def
        
        pipelines = flow_def.get("pipelines", {})
        
        for pipeline_name, steps in pipelines.items():
            if target_pipeline and pipeline_name != target_pipeline:
                continue
            
            if not isinstance(steps, list):
                continue
            
            index = self._find_step_index(steps, target_step)
            if index >= 0:
                if position == "after":
                    index += 1
                
                for j, new_step in enumerate(new_steps):
                    steps.insert(index + j, copy.deepcopy(new_step))
        
        return flow_def
    
    def _action_replace(
        self,
        flow_def: Dict[str, Any],
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """replace の実装"""
        target_step = modification.get("target_step", {})
        new_steps = modification.get("steps", [])
        target_pipeline = modification.get("pipeline")
        
        pipelines = flow_def.get("pipelines", {})
        
        for pipeline_name, steps in pipelines.items():
            if target_pipeline and pipeline_name != target_pipeline:
                continue
            
            if not isinstance(steps, list):
                continue
            
            index = self._find_step_index(steps, target_step)
            if index >= 0:
                # 元のステップを削除
                steps.pop(index)
                # 新しいステップを挿入
                for j, new_step in enumerate(new_steps):
                    steps.insert(index + j, copy.deepcopy(new_step))
        
        return flow_def
    
    def _action_wrap_loop(
        self,
        flow_def: Dict[str, Any],
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """wrap_with_loop の実装"""
        target_steps = modification.get("target_steps", [])  # ステップIDのリスト
        loop_config = modification.get("loop_config", {})
        target_pipeline = modification.get("pipeline")
        
        if not target_steps:
            return flow_def
        
        pipelines = flow_def.get("pipelines", {})
        
        for pipeline_name, steps in pipelines.items():
            if target_pipeline and pipeline_name != target_pipeline:
                continue
            
            if not isinstance(steps, list):
                continue
            
            # ターゲットステップのインデックスを収集
            indices = []
            for target_id in target_steps:
                for i, step in enumerate(steps):
                    if step.get("id") == target_id:
                        indices.append(i)
                        break
            
            if not indices:
                continue
            
            # 連続する範囲を特定
            indices.sort()
            start_idx = indices[0]
            end_idx = indices[-1]
            
            # 対象ステップを抽出
            loop_steps = steps[start_idx:end_idx + 1]
            
            # loopステップを作成
            loop_step = {
                "type": "loop",
                "exit_when": loop_config.get("exit_condition", "false"),
                "max_iterations": loop_config.get("max_iterations", 10),
                "steps": copy.deepcopy(loop_steps)
            }
            
            # 元のステップを削除してloopステップを挿入
            del steps[start_idx:end_idx + 1]
            steps.insert(start_idx, loop_step)
        
        return flow_def
    
    def _action_remove(
        self,
        flow_def: Dict[str, Any],
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """remove の実装"""
        target_step = modification.get("target_step", {})
        target_pipeline = modification.get("pipeline")
        
        pipelines = flow_def.get("pipelines", {})
        
        for pipeline_name, steps in pipelines.items():
            if target_pipeline and pipeline_name != target_pipeline:
                continue
            
            if not isinstance(steps, list):
                continue
            
            index = self._find_step_index(steps, target_step)
            if index >= 0:
                steps.pop(index)
        
        return flow_def
    
    def _action_set_property(
        self,
        flow_def: Dict[str, Any],
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """set_property の実装"""
        target_step = modification.get("target_step", {})
        properties = modification.get("properties", {})
        target_pipeline = modification.get("pipeline")
        
        pipelines = flow_def.get("pipelines", {})
        
        for pipeline_name, steps in pipelines.items():
            if target_pipeline and pipeline_name != target_pipeline:
                continue
            
            if not isinstance(steps, list):
                continue
            
            index = self._find_step_index(steps, target_step)
            if index >= 0:
                for key, value in properties.items():
                    steps[index][key] = copy.deepcopy(value)
        
        return flow_def
    
    def get_applied_modifiers(self) -> List[Dict[str, Any]]:
        """適用済みのmodifier情報を取得"""
        with self._lock:
            return list(self._applied_modifiers)
    
    def clear_applied(self) -> None:
        """適用済み情報をクリア"""
        with self._lock:
            self._applied_modifiers.clear()


# グローバルインスタンス
_global_flow_composer: Optional[FlowComposer] = None
_composer_lock = threading.Lock()


def get_flow_composer() -> FlowComposer:
    """グローバルなFlowComposerインスタンスを取得"""
    global _global_flow_composer
    if _global_flow_composer is None:
        with _composer_lock:
            if _global_flow_composer is None:
                _global_flow_composer = FlowComposer()
    return _global_flow_composer


def reset_flow_composer() -> FlowComposer:
    """FlowComposerをリセット（テスト用）"""
    global _global_flow_composer
    with _composer_lock:
        _global_flow_composer = FlowComposer()
    return _global_flow_composer
'''

write_file("core_runtime/flow_composer.py", flow_composer_py)

# =============================================================================
# 3. 新規ファイル: flow/core/00_startup.flow.yaml
# =============================================================================

startup_flow_yaml = '''# Rumi AI OS - Core Startup Flow
# 
# 公式Flow: Kernel初期化に必要な最小限の処理のみ定義
# このファイルはecosystemによる編集不可
#
# 処理内容:
# 1. マウントシステム初期化
# 2. Packレジストリ読み込み
# 3. アクティブエコシステム設定読み込み
# 4. コンポーネントフェーズ実行（setup, runtime_boot）
# 5. サービス公開

flow_version: "2.0"

defaults:
  fail_soft: true
  on_missing_handler: skip

pipelines:
  startup:
    # === Phase 1: 基盤初期化 ===
    - id: core.mounts
      run:
        handler: "kernel:mounts.init"
        args:
          mounts_file: "user_data/mounts.json"

    - id: core.registry
      run:
        handler: "kernel:registry.load"
        args:
          ecosystem_dir: "ecosystem"

    - id: core.active_ecosystem
      run:
        handler: "kernel:active_ecosystem.load"
        args:
          config_file: "user_data/active_ecosystem.json"

    # === Phase 2: コンポーネント初期化 ===
    - id: components.setup
      run:
        handler: "component_phase:setup"
        args:
          filename: "setup.py"

    # === Phase 3: Flow合成（オプション） ===
    # ecosystem側でflow.modifierが登録されていれば適用
    - id: core.flow_compose
      optional: true
      run:
        handler: "kernel:flow.compose"
        args: {}

    # === Phase 4: ランタイム起動 ===
    - id: components.runtime_boot
      run:
        handler: "component_phase:runtime_boot"
        args:
          filename: "runtime_boot.py"

    # === Phase 5: サービス公開 ===
    - id: core.interfaces_publish
      run:
        handler: "kernel:interfaces.publish"
        args: {}
'''

write_file("flow/core/00_startup.flow.yaml", startup_flow_yaml)

# =============================================================================
# 4. 新規ファイル: flow/ecosystem/.gitkeep
# =============================================================================

gitkeep_content = '''# ecosystem用Flowディレクトリ
# 
# このディレクトリにはecosystemコンポーネントが作成・編集するFlowを配置します。
# 
# 例:
# - message.flow.yaml: メッセージ処理パイプライン
# - ai_client.flow.yaml: AI呼び出しサブFlow
# - tool_execution.flow.yaml: ツール実行サブFlow
#
# Flowの作成・編集はecosystemコンポーネントのsetup.pyまたは
# flow_hooks.pyから行います（権限が必要）。
'''

write_file("flow/ecosystem/.gitkeep", gitkeep_content)

# =============================================================================
# 5. 更新: core_runtime/kernel.py (完全置き換え)
# =============================================================================

kernel_py = '''"""
kernel.py - Flow Runner(用途非依存カーネル)
async対応、Flow Hook、タイムアウト、循環検出対応版
"""

from __future__ import annotations

import copy
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
from .function_alias import FunctionAliasRegistry, get_function_alias_registry
from .flow_composer import FlowComposer, get_flow_composer


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
        
        # InstallJournalにInterfaceRegistryを設定
        self.install_journal.set_interface_registry(self.interface_registry)
        
        self._init_kernel_handlers()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _init_kernel_handlers(self) -> None:
        self._kernel_handlers = {
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
        """
        Flowを読み込む
        
        読み込み順序:
        1. flow/core/*.flow.yaml (公式、必須)
        2. flow/ecosystem/*.flow.yaml (ecosystem用、オプション)
        3. 引数で指定されたパス（オプション）
        
        同名のpipelineは後勝ち（ecosystemがcoreを上書き可能）
        """
        if path:
            return self._load_single_flow(Path(path))
        
        merged = {
            "flow_version": "2.0",
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {}
        }
        
        # 1. flow/core/ から読み込み（公式）
        core_dir = Path("flow/core")
        if core_dir.exists():
            yaml_files = sorted(core_dir.glob("*.flow.yaml"))
            for yaml_file in yaml_files:
                try:
                    single = self._load_single_flow(yaml_file)
                    merged = self._merge_flow(merged, single, yaml_file)
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.core.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="success",
                        meta={"file": str(yaml_file), "source": "core"}
                    )
                except Exception as e:
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.core.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="failed",
                        error=e,
                        meta={"file": str(yaml_file), "source": "core"}
                    )
        
        # 2. flow/ecosystem/ から読み込み（ecosystem用）
        ecosystem_dir = Path("flow/ecosystem")
        if ecosystem_dir.exists():
            yaml_files = sorted(ecosystem_dir.glob("*.flow.yaml"))
            for yaml_file in yaml_files:
                try:
                    single = self._load_single_flow(yaml_file)
                    merged = self._merge_flow(merged, single, yaml_file)
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.ecosystem.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="success",
                        meta={"file": str(yaml_file), "source": "ecosystem"}
                    )
                except Exception as e:
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.ecosystem.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="failed",
                        error=e,
                        meta={"file": str(yaml_file), "source": "ecosystem"}
                    )
        
        # 3. 後方互換: flow/ 直下も読み込み（将来的に廃止予定）
        flow_dir = Path("flow")
        if flow_dir.exists():
            yaml_files = sorted(flow_dir.glob("*.flow.yaml"))
            for yaml_file in yaml_files:
                try:
                    single = self._load_single_flow(yaml_file)
                    merged = self._merge_flow(merged, single, yaml_file)
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.legacy.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="success",
                        meta={"file": str(yaml_file), "source": "legacy"}
                    )
                except Exception as e:
                    self.diagnostics.record_step(
                        phase="startup",
                        step_id=f"flow.load.legacy.{yaml_file.name}",
                        handler="kernel:flow.load",
                        status="failed",
                        error=e,
                        meta={"file": str(yaml_file), "source": "legacy"}
                    )
        
        # フォールバック: 何も読み込めなかった場合
        if not merged["pipelines"]:
            self._flow = self._minimal_fallback_flow()
            return self._flow
        
        self._flow = merged
        return self._flow

    def _merge_flow(self, base: Dict[str, Any], new: Dict[str, Any], source_file: Path = None) -> Dict[str, Any]:
        """
        Flow定義をマージ
        
        - defaultsは更新（後勝ち）
        - pipelinesは各パイプラインのstepsを結合または上書き
        """
        result = copy.deepcopy(base)
        
        # defaults をマージ
        if "defaults" in new:
            result["defaults"].update(new["defaults"])
        
        # pipelines をマージ
        for pipeline_name, steps in new.get("pipelines", {}).items():
            if not isinstance(steps, list):
                continue
            
            if pipeline_name not in result["pipelines"]:
                result["pipelines"][pipeline_name] = []
            
            # ステップを追加（同名IDは上書き）
            existing_ids = {s.get("id") for s in result["pipelines"][pipeline_name] if s.get("id")}
            
            for step in steps:
                step_id = step.get("id")
                if step_id and step_id in existing_ids:
                    # 同名IDのステップを置換
                    result["pipelines"][pipeline_name] = [
                        step if s.get("id") == step_id else s
                        for s in result["pipelines"][pipeline_name]
                    ]
                else:
                    result["pipelines"][pipeline_name].append(step)
        
        return result

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

    def run_pipeline(self, pipeline_name: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        汎用パイプライン実行
        
        任意の名前のパイプラインを実行する。run_message()やrun_message_stream()の
        汎用版として使用可能。
        
        Args:
            pipeline_name: 実行するパイプライン名（flowのpipelines配下のキー）
            context: 追加のコンテキスト（chat_id, payload等）
        
        Returns:
            実行結果を含むコンテキスト辞書
        
        Example:
            # "custom_process" パイプラインを実行
            result = kernel.run_pipeline("custom_process", {"input": data})
        """
        flow = self._flow or self.load_flow()
        defaults = flow.get("defaults", {}) if isinstance(flow, dict) else {}
        fail_soft_default = bool(defaults.get("fail_soft", True))
        pipelines = flow.get("pipelines", {})
        steps = pipelines.get(pipeline_name, []) if isinstance(pipelines, dict) else []
        steps = steps if isinstance(steps, list) else []
        
        ctx = self._build_kernel_context()
        ctx["_flow_defaults"] = {
            "fail_soft": fail_soft_default, 
            "on_missing_handler": str(defaults.get("on_missing_handler", "skip")).lower()
        }
        if context:
            ctx.update(context)
        
        self.diagnostics.record_step(
            phase=pipeline_name, 
            step_id=f"{pipeline_name}.pipeline.start", 
            handler=f"kernel:{pipeline_name}.run",
            status="success", 
            meta={"step_count": len(steps), "pipeline": pipeline_name}
        )
        
        aborted = False
        for step in steps:
            if aborted:
                break
            try:
                aborted = self._execute_flow_step(step, phase=pipeline_name, ctx=ctx)
            except Exception as e:
                self.diagnostics.record_step(
                    phase=pipeline_name, 
                    step_id=f"{pipeline_name}.pipeline.internal_error",
                    handler=f"kernel:{pipeline_name}.run", 
                    status="failed", 
                    error=e
                )
                if not fail_soft_default:
                    break
        
        self.diagnostics.record_step(
            phase=pipeline_name, 
            step_id=f"{pipeline_name}.pipeline.end", 
            handler=f"kernel:{pipeline_name}.run",
            status="success" if not aborted else "failed", 
            meta={"aborted": aborted, "pipeline": pipeline_name}
        )
        
        return ctx

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
                elif step_type == "flow":
                    # サブFlow呼び出し
                    ctx, step_result = await self._execute_sub_flow_step(step, ctx)
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

    async def _execute_sub_flow_step(self, step: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        """
        サブFlowステップを実行
        
        ステップ形式:
        - type: flow
          flow: flow_name          # 実行するFlow名
          args:                     # 子Flowのctxに渡す引数
            key1: value1
            key2: "${ctx.parent_value}"
          output: result_key       # 結果を格納するキー（省略可）
        
        Args:
            step: ステップ定義
            ctx: 親のコンテキスト
        
        Returns:
            (更新された親ctx, 子Flowの結果)
        """
        flow_name = step.get("flow")
        if not flow_name:
            return ctx, None
        
        # 循環検出
        call_stack = ctx.get("_flow_call_stack", [])
        if flow_name in call_stack:
            error_msg = f"Recursive flow detected: {' -> '.join(call_stack)} -> {flow_name}"
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.recursive",
                handler="kernel:subflow",
                status="failed",
                error={"type": "RecursiveFlowError", "message": error_msg}
            )
            return ctx, {"_error": error_msg}
        
        # 子ctxを作成（親ctxのコピー）
        child_ctx = copy.deepcopy(ctx)
        child_ctx["_flow_call_stack"] = call_stack + [flow_name]
        child_ctx["_parent_flow_id"] = ctx.get("_flow_id")
        
        # argsを解決して子ctxに設定
        args = step.get("args", {})
        resolved_args = self._resolve_value(args, ctx)
        if isinstance(resolved_args, dict):
            child_ctx.update(resolved_args)
        
        # サブFlowを実行
        try:
            # まずIRから検索
            flow_def = self.interface_registry.get(f"flow.{flow_name}", strategy="last")
            
            # IRになければflow/ecosystem/から検索
            if flow_def is None:
                ecosystem_flow_path = Path("flow/ecosystem") / f"{flow_name}.flow.yaml"
                if ecosystem_flow_path.exists():
                    flow_def = self._load_single_flow(ecosystem_flow_path)
                    # pipelinesの最初のパイプラインをstepsとして使用
                    if "pipelines" in flow_def:
                        first_pipeline = list(flow_def["pipelines"].values())[0]
                        flow_def = {"steps": first_pipeline}
            
            if flow_def is None:
                self.diagnostics.record_step(
                    phase="flow",
                    step_id=f"subflow.{flow_name}.not_found",
                    handler="kernel:subflow",
                    status="failed",
                    error={"type": "FlowNotFoundError", "message": f"Flow '{flow_name}' not found"}
                )
                return ctx, {"_error": f"Flow '{flow_name}' not found"}
            
            # stepsを取得
            steps = flow_def.get("steps", [])
            if not steps and "pipelines" in flow_def:
                # pipelinesがある場合は最初のパイプラインを使用
                first_pipeline = list(flow_def["pipelines"].values())[0]
                steps = first_pipeline if isinstance(first_pipeline, list) else []
            
            # 子Flowを実行
            child_ctx["_flow_id"] = flow_name
            child_ctx = await self._execute_steps_async(steps, child_ctx)
            
            # 結果を取得
            result = child_ctx.get("output") or child_ctx.get("result") or child_ctx
            
            # outputが指定されていれば親ctxに格納
            output_key = step.get("output")
            if output_key:
                ctx[output_key] = result
            
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.complete",
                handler="kernel:subflow",
                status="success",
                meta={"flow_name": flow_name, "output_key": output_key}
            )
            
            return ctx, result
            
        except Exception as e:
            self.diagnostics.record_step(
                phase="flow",
                step_id=f"subflow.{flow_name}.error",
                handler="kernel:subflow",
                status="failed",
                error=e,
                meta={"flow_name": flow_name}
            )
            return ctx, {"_error": str(e)}

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
        
        # PermissionManagerを追加
        try:
            from .permission_manager import get_permission_manager
            ctx["permission_manager"] = get_permission_manager()
        except ImportError:
            pass
        
        # FunctionAliasRegistryを追加
        try:
            ctx["function_alias_registry"] = get_function_alias_registry()
        except Exception:
            pass
        
        # FlowComposerを追加
        try:
            ctx["flow_composer"] = get_flow_composer()
        except Exception:
            pass
        
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

    def _h_flow_compose(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Flow合成を実行
        
        IRに登録されたflow.modifierを収集し、現在のFlow定義に適用する。
        """
        try:
            composer = get_flow_composer()
            alias_registry = get_function_alias_registry()
            composer.set_alias_registry(alias_registry)
            
            # modifierを収集
            modifiers = composer.collect_modifiers(self.interface_registry)
            
            if not modifiers:
                return {
                    "_kernel_step_status": "skipped",
                    "_kernel_step_meta": {"reason": "no_modifiers"}
                }
            
            # capabilitiesを収集
            capabilities = {}
            all_caps = self.interface_registry.get("component.capabilities", strategy="all") or []
            for cap_dict in all_caps:
                if isinstance(cap_dict, dict):
                    capabilities.update(cap_dict)
            
            # 修正を適用
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
'''

write_file("core_runtime/kernel.py", kernel_py)

# =============================================================================
# 6. 更新: core_runtime/__init__.py (完全置き換え)
# =============================================================================

init_py = '''"""
core_runtime package
"""

from .kernel import Kernel, KernelConfig
from .diagnostics import Diagnostics
from .install_journal import InstallJournal, InstallJournalConfig
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor
from .permission_manager import PermissionManager, get_permission_manager
from .function_alias import FunctionAliasRegistry, get_function_alias_registry
from .flow_composer import FlowComposer, FlowModifier, get_flow_composer

__all__ = [
    "Kernel",
    "KernelConfig",
    "Diagnostics",
    "InstallJournal",
    "InstallJournalConfig",
    "InterfaceRegistry",
    "EventBus",
    "ComponentLifecycleExecutor",
    "PermissionManager",
    "get_permission_manager",
    "FunctionAliasRegistry",
    "get_function_alias_registry",
    "FlowComposer",
    "FlowModifier",
    "get_flow_composer",
]
'''

write_file("core_runtime/__init__.py", init_py)

# =============================================================================
# 7. 古いflowファイルの移動/削除についての説明を出力
# =============================================================================

print("\n" + "="*60)
print("実装完了")
print("="*60)
print("""
作成/更新されたファイル:
  ✓ core_runtime/function_alias.py (新規)
  ✓ core_runtime/flow_composer.py (新規)
  ✓ flow/core/00_startup.flow.yaml (新規)
  ✓ flow/ecosystem/.gitkeep (新規)
  ✓ core_runtime/kernel.py (更新)
  ✓ core_runtime/__init__.py (更新)

次のステップ:
  1. 既存の flow/*.flow.yaml ファイルを整理してください:
     - flow/00_core.flow.yaml → 削除（flow/core/00_startup.flow.yamlで置き換え）
     - flow/10_components.flow.yaml → 削除または flow/core/ に移動
     - flow/20_services.flow.yaml → 削除または flow/core/ に移動
     - flow/50_message.flow.yaml → flow/ecosystem/ に移動

  2. ecosystem側でエイリアスを登録するコンポーネントを作成:
     例: ecosystem/default/backend/components/aliases/setup.py

  3. 必要に応じてflow.modifierを登録するコンポーネントを作成
""")
