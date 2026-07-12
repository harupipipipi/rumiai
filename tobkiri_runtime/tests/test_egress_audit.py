"""
Egress Proxy 監査ログのテスト

deny/allow/失敗の監査ログ記録をテストする。
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.network_grant_manager import (
    NetworkGrantManager,
    NetworkGrant,
    NetworkCheckResult,
    reset_network_grant_manager,
)
from core_runtime.audit_logger import (
    AuditLogger,
    reset_audit_logger,
)


class TestNetworkGrantAuditLogging(unittest.TestCase):
    """ネットワーク権限チェックの監査ログテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.grants_dir = os.path.join(self.temp_dir, "grants")
        self.audit_dir = os.path.join(self.temp_dir, "audit")
        
        os.makedirs(self.grants_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)
        
        self.grant_manager = NetworkGrantManager(grants_dir=self.grants_dir)
        self.audit_logger = reset_audit_logger(self.audit_dir)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _get_audit_entries(self, category: str = "network") -> list:
        """監査ログエントリを取得"""
        self.audit_logger.flush()
        entries = []
        
        for log_file in Path(self.audit_dir).glob(f"{category}_*.jsonl"):
            with open(log_file, 'r') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        
        return entries
    
    def test_allowed_access_logs_correctly(self):
        """許可されたアクセスが正しくログに記録される"""
        # Grant を作成
        self.grant_manager.grant_network_access(
            pack_id="test_pack",
            allowed_domains=["api.example.com"],
            allowed_ports=[443]
        )
        
        # アクセスチェック
        result = self.grant_manager.check_access("test_pack", "api.example.com", 443)
        
        self.assertTrue(result.allowed)
        
        # 監査ログを確認
        entries = self._get_audit_entries()
        
        # アクセスチェックのエントリを探す
        check_entries = [e for e in entries if e.get("details", {}).get("check_type") == "access_check"]
        self.assertTrue(len(check_entries) > 0)
        
        last_entry = check_entries[-1]
        self.assertTrue(last_entry.get("success"))
        self.assertEqual(last_entry.get("details", {}).get("allowed"), True)
        self.assertEqual(last_entry.get("details", {}).get("domain"), "api.example.com")
        self.assertEqual(last_entry.get("details", {}).get("port"), 443)
    
    def test_denied_access_logs_correctly(self):
        """拒否されたアクセスが正しくログに記録される"""
        # Grant を作成（異なるドメインのみ許可）
        self.grant_manager.grant_network_access(
            pack_id="test_pack",
            allowed_domains=["api.example.com"],
            allowed_ports=[443]
        )
        
        # 許可されていないドメインへのアクセスチェック
        result = self.grant_manager.check_access("test_pack", "evil.example.com", 443)
        
        self.assertFalse(result.allowed)
        
        # 監査ログを確認
        entries = self._get_audit_entries()
        
        # 拒否エントリを探す
        denied_entries = [e for e in entries if not e.get("success") and e.get("details", {}).get("check_type") == "access_check"]
        self.assertTrue(len(denied_entries) > 0)
        
        last_entry = denied_entries[-1]
        self.assertFalse(last_entry.get("success"))
        self.assertEqual(last_entry.get("details", {}).get("allowed"), False)
        self.assertIsNotNone(last_entry.get("rejection_reason"))
    
    def test_no_grant_logs_correctly(self):
        """Grant がない場合の拒否が正しくログに記録される"""
        # Grant なしでアクセスチェック
        result = self.grant_manager.check_access("unknown_pack", "api.example.com", 443)
        
        self.assertFalse(result.allowed)
        
        # 監査ログを確認
        entries = self._get_audit_entries()
        
        denied_entries = [e for e in entries if not e.get("success")]
        self.assertTrue(len(denied_entries) > 0)
        
        last_entry = denied_entries[-1]
        self.assertIn("No network grant", last_entry.get("rejection_reason", ""))
    
    def test_port_denied_logs_correctly(self):
        """ポートが拒否された場合のログ記録"""
        # 443のみ許可
        self.grant_manager.grant_network_access(
            pack_id="test_pack",
            allowed_domains=["api.example.com"],
            allowed_ports=[443]
        )
        
        # 80番ポートへのアクセス（拒否されるはず）
        result = self.grant_manager.check_access("test_pack", "api.example.com", 80)
        
        self.assertFalse(result.allowed)
        
        # 監査ログを確認
        entries = self._get_audit_entries()
        
        denied_entries = [e for e in entries if not e.get("success") and e.get("details", {}).get("port") == 80]
        self.assertTrue(len(denied_entries) > 0)


class TestEgressProxyAuditLogging(unittest.TestCase):
    """Egress Proxy の監査ログテスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audit_dir = os.path.join(self.temp_dir, "audit")
        os.makedirs(self.audit_dir, exist_ok=True)
        
        self.audit_logger = reset_audit_logger(self.audit_dir)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _get_audit_entries(self, category: str = "network") -> list:
        """監査ログエントリを取得"""
        self.audit_logger.flush()
        entries = []
        
        for log_file in Path(self.audit_dir).glob(f"{category}_*.jsonl"):
            with open(log_file, 'r') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        
        return entries
    
    def test_audit_entry_contains_allowed_field(self):
        """監査エントリに allowed フィールドが含まれる"""
        # 直接 log_network_event を呼び出してテスト
        self.audit_logger.log_network_event(
            pack_id="test_pack",
            domain="api.example.com",
            port=443,
            allowed=True,
            request_details={"method": "GET", "url": "https://api.example.com/test"}
        )
        
        entries = self._get_audit_entries()
        self.assertTrue(len(entries) > 0)
        
        last_entry = entries[-1]
        self.assertEqual(last_entry.get("details", {}).get("allowed"), True)
        self.assertTrue(last_entry.get("success"))
    
    def test_denied_request_audit_entry(self):
        """拒否されたリクエストの監査エントリ"""
        self.audit_logger.log_network_event(
            pack_id="test_pack",
            domain="evil.com",
            port=443,
            allowed=False,
            reason="Domain not in allowed list",
            request_details={"method": "GET", "url": "https://evil.com/malware"}
        )
        
        entries = self._get_audit_entries()
        self.assertTrue(len(entries) > 0)
        
        last_entry = entries[-1]
        self.assertEqual(last_entry.get("details", {}).get("allowed"), False)
        self.assertFalse(last_entry.get("success"))
        self.assertEqual(last_entry.get("rejection_reason"), "Domain not in allowed list")
    
    def test_failed_request_audit_entry(self):
        """失敗したリクエスト（許可はされたが実行失敗）の監査エントリ"""
        self.audit_logger.log_network_event(
            pack_id="test_pack",
            domain="api.example.com",
            port=443,
            allowed=True,  # 許可はされた
            request_details={
                "method": "GET",
                "url": "https://api.example.com/test",
                "success": False,  # しかし実行は失敗
                "error": "Connection timeout"
            }
        )
        
        entries = self._get_audit_entries()
        self.assertTrue(len(entries) > 0)
        
        last_entry = entries[-1]
        # allowed=True なので success=True（許可された）
        self.assertTrue(last_entry.get("success"))
        self.assertEqual(last_entry.get("details", {}).get("allowed"), True)
        # しかし実行は失敗
        self.assertEqual(last_entry.get("details", {}).get("success"), False)
        self.assertEqual(last_entry.get("details", {}).get("error"), "Connection timeout")


class TestAuditLogIntegrity(unittest.TestCase):
    """監査ログの整合性テスト"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audit_dir = os.path.join(self.temp_dir, "audit")
        os.makedirs(self.audit_dir, exist_ok=True)
        
        self.audit_logger = reset_audit_logger(self.audit_dir)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_all_network_events_have_required_fields(self):
        """全てのネットワークイベントに必須フィールドがある"""
        # 様々なイベントを記録
        events = [
            {"pack_id": "pack1", "domain": "example.com", "port": 443, "allowed": True},
            {"pack_id": "pack2", "domain": "evil.com", "port": 80, "allowed": False, "reason": "Blocked"},
            {"pack_id": "pack3", "domain": "api.test.com", "port": 8080, "allowed": True},
        ]
        
        for event in events:
            self.audit_logger.log_network_event(**event)
        
        self.audit_logger.flush()
        
        # 全エントリを確認
        entries = []
        for log_file in Path(self.audit_dir).glob("network_*.jsonl"):
            with open(log_file, 'r') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        
        for entry in entries:
            # 必須フィールドの確認
            self.assertIn("ts", entry)
            self.assertIn("category", entry)
            self.assertEqual(entry["category"], "network")
            self.assertIn("success", entry)
            self.assertIn("details", entry)
            self.assertIn("domain", entry["details"])
            self.assertIn("port", entry["details"])
            self.assertIn("allowed", entry["details"])


if __name__ == "__main__":
    unittest.main()
