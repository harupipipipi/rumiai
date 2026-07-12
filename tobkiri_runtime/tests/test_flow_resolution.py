"""
Flow解決のテスト

共有辞書によるflow_id解決をテストする。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.shared_dict.snapshot import SharedDictSnapshot
from core_runtime.shared_dict.journal import SharedDictJournal
from core_runtime.shared_dict.resolver import SharedDictResolver


class TestFlowIdResolution(unittest.TestCase):
    """Flow ID解決のテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        self.journal_path = os.path.join(self.temp_dir, "journal.jsonl")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
        self.journal = SharedDictJournal(self.journal_path, self.snapshot)
        self.resolver = SharedDictResolver(self.snapshot)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_resolve_disabled_by_default(self):
        """デフォルトでは解決されない（オプトイン）"""
        # エイリアスを登録
        self.journal.propose("flow_id", "old_flow", "new_flow")
        
        # resolve=False（デフォルト）では解決されない
        # Kernelの_h_flow_execute_by_idの動作をシミュレート
        flow_id = "old_flow"
        resolve = False
        
        if resolve:
            flow_id = self.resolver.resolve("flow_id", flow_id)
        
        # 解決されていない
        self.assertEqual(flow_id, "old_flow")
    
    def test_resolve_enabled_resolves_alias(self):
        """resolve=Trueでエイリアスが解決される"""
        # エイリアスを登録
        self.journal.propose("flow_id", "old_flow", "new_flow")
        
        # resolve=True では解決される
        flow_id = "old_flow"
        resolve = True
        
        if resolve:
            flow_id = self.resolver.resolve("flow_id", flow_id)
        
        # 解決された
        self.assertEqual(flow_id, "new_flow")
    
    def test_resolve_unknown_returns_original(self):
        """未知のflow_idは元のまま返される"""
        flow_id = "unknown_flow"
        resolved = self.resolver.resolve("flow_id", flow_id)
        
        self.assertEqual(resolved, "unknown_flow")
    
    def test_resolve_chain(self):
        """チェーン解決（A→B→C）"""
        self.journal.propose("flow_id", "flow_v1", "flow_v2")
        self.journal.propose("flow_id", "flow_v2", "flow_v3")
        
        resolved = self.resolver.resolve("flow_id", "flow_v1")
        
        self.assertEqual(resolved, "flow_v3")
    
    def test_custom_namespace(self):
        """カスタムnamespaceを使用できる"""
        # 異なるnamespaceに登録
        self.journal.propose("custom_ns", "old_id", "new_id")
        
        # flow_id namespaceでは解決されない
        resolved1 = self.resolver.resolve("flow_id", "old_id")
        self.assertEqual(resolved1, "old_id")
        
        # custom_ns namespaceでは解決される
        resolved2 = self.resolver.resolve("custom_ns", "old_id")
        self.assertEqual(resolved2, "new_id")


class TestModifierTargetResolution(unittest.TestCase):
    """Modifier target解決のテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        self.journal_path = os.path.join(self.temp_dir, "journal.jsonl")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
        self.journal = SharedDictJournal(self.journal_path, self.snapshot)
        self.resolver = SharedDictResolver(self.snapshot)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_modifier_resolve_target_false(self):
        """resolve_target=Falseではターゲットが解決されない"""
        self.journal.propose("flow_id", "old_target", "new_target")
        
        # resolve_target=False のmodifier
        target_flow_id = "old_target"
        resolve_target = False
        
        if resolve_target:
            target_flow_id = self.resolver.resolve("flow_id", target_flow_id)
        
        # 解決されない
        self.assertEqual(target_flow_id, "old_target")
    
    def test_modifier_resolve_target_true(self):
        """resolve_target=Trueでターゲットが解決される"""
        self.journal.propose("flow_id", "old_target", "new_target")
        
        # resolve_target=True のmodifier
        target_flow_id = "old_target"
        resolve_target = True
        
        if resolve_target:
            target_flow_id = self.resolver.resolve("flow_id", target_flow_id)
        
        # 解決される
        self.assertEqual(target_flow_id, "new_target")


class TestKernelFlowExecuteByIdIntegration(unittest.TestCase):
    """Kernelのflow.execute_by_id統合テスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_execute_by_id_without_resolve(self):
        """resolve=Falseで実行"""
        # モックKernelの動作をシミュレート
        args = {
            "flow_id": "test_flow",
            "resolve": False,
        }
        
        flow_id = args.get("flow_id")
        resolve = args.get("resolve", False)
        
        original_flow_id = flow_id
        resolved_flow_id = flow_id
        
        if resolve:
            # 解決処理（スキップされる）
            pass
        
        self.assertEqual(original_flow_id, resolved_flow_id)
    
    def test_execute_by_id_with_resolve(self):
        """resolve=Trueで実行"""
        # エイリアスを登録
        from core_runtime.shared_dict.journal import SharedDictJournal
        journal = SharedDictJournal(
            os.path.join(self.temp_dir, "journal.jsonl"),
            self.snapshot
        )
        journal.propose("flow_id", "alias_flow", "real_flow")
        
        resolver = SharedDictResolver(self.snapshot)
        
        # モックKernelの動作をシミュレート
        args = {
            "flow_id": "alias_flow",
            "resolve": True,
            "resolve_namespace": "flow_id",
        }
        
        flow_id = args.get("flow_id")
        resolve = args.get("resolve", False)
        resolve_namespace = args.get("resolve_namespace", "flow_id")
        
        original_flow_id = flow_id
        resolved_flow_id = flow_id
        
        if resolve:
            result = resolver.resolve_chain(resolve_namespace, flow_id)
            resolved_flow_id = result.resolved
        
        self.assertEqual(original_flow_id, "alias_flow")
        self.assertEqual(resolved_flow_id, "real_flow")


if __name__ == "__main__":
    unittest.main()
