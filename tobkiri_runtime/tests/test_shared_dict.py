"""
共有辞書のテスト

循環検出、衝突検出、ホップ上限などをテストする。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.shared_dict.snapshot import SharedDictSnapshot, reset_shared_dict_snapshot
from core_runtime.shared_dict.journal import SharedDictJournal, ProposalStatus, reset_shared_dict_journal
from core_runtime.shared_dict.resolver import SharedDictResolver, reset_shared_dict_resolver


class TestSharedDictSnapshot(unittest.TestCase):
    """スナップショットのテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_rule_success(self):
        """ルール追加が成功する"""
        result = self.snapshot.add_rule("test_ns", "A", "B")
        self.assertTrue(result)
        
        rule = self.snapshot.get_rule("test_ns", "A")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.token, "A")
        self.assertEqual(rule.value, "B")
    
    def test_add_duplicate_rule_success(self):
        """同じルールの重複追加は成功する（冪等）"""
        self.snapshot.add_rule("test_ns", "A", "B")
        result = self.snapshot.add_rule("test_ns", "A", "B")
        self.assertTrue(result)
    
    def test_add_conflicting_rule_fails(self):
        """同じtokenに異なるvalueを追加すると失敗する"""
        self.snapshot.add_rule("test_ns", "A", "B")
        result = self.snapshot.add_rule("test_ns", "A", "C")
        self.assertFalse(result)
    
    def test_remove_rule(self):
        """ルール削除が成功する"""
        self.snapshot.add_rule("test_ns", "A", "B")
        result = self.snapshot.remove_rule("test_ns", "A")
        self.assertTrue(result)
        
        rule = self.snapshot.get_rule("test_ns", "A")
        self.assertIsNone(rule)


class TestSharedDictJournal(unittest.TestCase):
    """ジャーナルのテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        self.journal_path = os.path.join(self.temp_dir, "journal.jsonl")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
        self.journal = SharedDictJournal(self.journal_path, self.snapshot)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_propose_success(self):
        """提案が成功する"""
        result = self.journal.propose("test_ns", "A", "B", {"source_pack_id": "test"})
        
        self.assertTrue(result.accepted)
        self.assertEqual(result.status, ProposalStatus.ACCEPTED)
    
    def test_propose_conflict(self):
        """衝突時に拒否される"""
        self.journal.propose("test_ns", "A", "B")
        result = self.journal.propose("test_ns", "A", "C")
        
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, ProposalStatus.CONFLICT)
    
    def test_propose_cycle_detection(self):
        """循環が検出される（A→B, B→A）"""
        self.journal.propose("test_ns", "A", "B")
        result = self.journal.propose("test_ns", "B", "A")
        
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, ProposalStatus.CYCLE_DETECTED)
    
    def test_propose_longer_cycle_detection(self):
        """長い循環が検出される（A→B→C→A）"""
        self.journal.propose("test_ns", "A", "B")
        self.journal.propose("test_ns", "B", "C")
        result = self.journal.propose("test_ns", "C", "A")
        
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, ProposalStatus.CYCLE_DETECTED)
    
    def test_history(self):
        """履歴が記録される"""
        self.journal.propose("test_ns", "A", "B")
        self.journal.propose("test_ns", "C", "D")
        
        history = self.journal.get_history()
        self.assertEqual(len(history), 2)


class TestSharedDictResolver(unittest.TestCase):
    """リゾルバのテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
        self.resolver = SharedDictResolver(self.snapshot, max_hops=5)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_resolve_not_found(self):
        """ルールがない場合は元の値を返す"""
        result = self.resolver.resolve("test_ns", "unknown")
        self.assertEqual(result, "unknown")
    
    def test_resolve_single_hop(self):
        """単一ホップの解決"""
        self.snapshot.add_rule("test_ns", "A", "B")
        
        result = self.resolver.resolve("test_ns", "A")
        self.assertEqual(result, "B")
    
    def test_resolve_chain(self):
        """チェーン解決（A→B→C）"""
        self.snapshot.add_rule("test_ns", "A", "B")
        self.snapshot.add_rule("test_ns", "B", "C")
        
        result = self.resolver.resolve("test_ns", "A")
        self.assertEqual(result, "C")
    
    def test_resolve_max_hops(self):
        """ホップ上限に達した場合"""
        # 長いチェーンを作成
        for i in range(10):
            self.snapshot.add_rule("test_ns", f"V{i}", f"V{i+1}")
        
        result = self.resolver.resolve_chain("test_ns", "V0")
        self.assertTrue(result.max_hops_reached)
    
    def test_explain(self):
        """解決の説明が取得できる"""
        self.snapshot.add_rule("test_ns", "A", "B", provenance={"source": "test"})
        self.snapshot.add_rule("test_ns", "B", "C", provenance={"source": "test2"})
        
        result = self.resolver.explain("test_ns", "A")
        
        self.assertEqual(result.original, "A")
        self.assertEqual(result.resolved, "C")
        self.assertEqual(len(result.hops), 3)  # A, B, C


class TestCycleDetectionEdgeCases(unittest.TestCase):
    """循環検出のエッジケーステスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "snapshot.json")
        self.journal_path = os.path.join(self.temp_dir, "journal.jsonl")
        
        self.snapshot = SharedDictSnapshot(self.snapshot_path)
        self.journal = SharedDictJournal(self.journal_path, self.snapshot)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_self_reference_cycle(self):
        """自己参照（A→A）が検出される"""
        result = self.journal.propose("test_ns", "A", "A")
        
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, ProposalStatus.CYCLE_DETECTED)
    
    def test_different_namespaces_no_conflict(self):
        """異なるnamespaceでは衝突しない"""
        result1 = self.journal.propose("ns1", "A", "B")
        result2 = self.journal.propose("ns2", "A", "C")
        
        self.assertTrue(result1.accepted)
        self.assertTrue(result2.accepted)


if __name__ == "__main__":
    unittest.main()
