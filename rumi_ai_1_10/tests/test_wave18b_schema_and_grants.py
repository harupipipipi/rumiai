"""
test_wave18b_schema_and_grants.py - W18-B テスト

スキーマバリデーション、SecretsGrantManager、承認フロー、API の 22 テストケース。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# pack_validator バリデーションロジック（抽出テスト用ヘルパー）
# ---------------------------------------------------------------------------

_KEY_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")


def _validate_new_fields(pack_id: str, eco_data: dict) -> List[str]:
    """pack_validator に追加されるバリデーションロジックを再現"""
    errors: List[str] = []

    # required_secrets
    if "required_secrets" in eco_data:
        rs = eco_data["required_secrets"]
        if not isinstance(rs, list):
            errors.append(f"[{pack_id}] required_secrets must be a list")
        else:
            for key in rs:
                if not isinstance(key, str) or not _KEY_PATTERN.match(key):
                    errors.append(f"[{pack_id}] invalid secret key '{key}'")

    # required_network
    if "required_network" in eco_data:
        rn = eco_data["required_network"]
        if not isinstance(rn, dict):
            errors.append(f"[{pack_id}] required_network must be a dict")
        else:
            ad = rn.get("allowed_domains", [])
            ap = rn.get("allowed_ports", [])
            if not isinstance(ad, list):
                errors.append(f"[{pack_id}] allowed_domains must be a list")
            if not isinstance(ap, list):
                errors.append(
                    f"[{pack_id}] allowed_ports must be a list of integers"
                )
            else:
                for p in ap:
                    if not isinstance(p, int) or p < 0 or p > 65535:
                        errors.append(f"[{pack_id}] invalid port {p}")

    # host_execution
    if "host_execution" in eco_data:
        he = eco_data["host_execution"]
        if not isinstance(he, bool):
            errors.append(f"[{pack_id}] host_execution must be a boolean")

    return errors


# ===========================================================================
# Test: スキーマバリデーション (1-7)
# ===========================================================================


class TestSchemaValidation(unittest.TestCase):
    """ecosystem.json 新フィールドのバリデーションテスト"""

    # 1. required_secrets が正常な配列 → バリデーション通過
    def test_01_required_secrets_valid(self):
        eco = {"required_secrets": ["OPENAI_API_KEY", "MY_SECRET_123"]}
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(errors, [])

    # 2. required_secrets が配列でない → エラー
    def test_02_required_secrets_not_list(self):
        eco = {"required_secrets": "OPENAI_API_KEY"}
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a list", errors[0])

    # 3. required_secrets のキーが無効パターン → エラー
    def test_03_required_secrets_invalid_key(self):
        eco = {"required_secrets": ["valid_KEY", "lowercase_bad"]}
        errors = _validate_new_fields("ai.test", eco)
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("invalid secret key" in e for e in errors))

    # 4. required_network が正常 → バリデーション通過
    def test_04_required_network_valid(self):
        eco = {
            "required_network": {
                "allowed_domains": ["api.openai.com", "*.openai.com"],
                "allowed_ports": [443, 80],
            }
        }
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(errors, [])

    # 5. required_network.allowed_ports に無効値 → エラー
    def test_05_required_network_invalid_port(self):
        eco = {
            "required_network": {
                "allowed_domains": ["example.com"],
                "allowed_ports": [443, -1, 99999],
            }
        }
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(len(errors), 2)  # -1 と 99999
        self.assertTrue(all("invalid port" in e for e in errors))

    # 6. host_execution が bool でない → エラー
    def test_06_host_execution_not_bool(self):
        eco = {"host_execution": "true"}
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a boolean", errors[0])

    # 7. 全フィールド省略 → バリデーション通過（全てオプション）
    def test_07_all_fields_omitted(self):
        eco = {"pack_id": "ai.test", "version": "1.0.0"}
        errors = _validate_new_fields("ai.test", eco)
        self.assertEqual(errors, [])


# ===========================================================================
# Test: SecretsGrantManager (8-17)
# ===========================================================================


class TestSecretsGrantManager(unittest.TestCase):
    """SecretsGrantManager のテスト"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="test_sgm_")
        self._grants_dir = os.path.join(self._tmpdir, "grants")
        # 固定の秘密鍵でテスト
        self._secret_key = "a" * 64

        from core_runtime.secrets_grant_manager import SecretsGrantManager
        self.manager = SecretsGrantManager(
            grants_dir=self._grants_dir,
            secret_key=self._secret_key,
        )

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # 8. grant_secret_access で Grant ファイルが作成される
    def test_08_grant_creates_file(self):
        self.manager.grant_secret_access("ai.openai", ["OPENAI_API_KEY"])
        grant_file = self.manager._get_grant_file("ai.openai")
        self.assertTrue(grant_file.exists())

    # 9. Grant ファイルに HMAC 署名が含まれる
    def test_09_grant_file_has_hmac(self):
        self.manager.grant_secret_access("ai.openai", ["OPENAI_API_KEY"])
        grant_file = self.manager._get_grant_file("ai.openai")
        with open(grant_file, "r") as f:
            data = json.load(f)
        self.assertIn("_hmac_signature", data)
        self.assertTrue(len(data["_hmac_signature"]) > 0)

    # 10. get_granted_keys が Grant 済みキーを返す
    def test_10_get_granted_keys(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A", "KEY_B"])
        keys = self.manager.get_granted_keys("ai.openai")
        self.assertEqual(sorted(keys), ["KEY_A", "KEY_B"])

    # 11. revoke_secret_access で指定キーが削除される
    def test_11_revoke_specific_keys(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A", "KEY_B", "KEY_C"])
        self.manager.revoke_secret_access("ai.openai", ["KEY_B"])
        keys = self.manager.get_granted_keys("ai.openai")
        self.assertEqual(sorted(keys), ["KEY_A", "KEY_C"])

    # 12. revoke_all で全キーが削除される
    def test_12_revoke_all(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A", "KEY_B"])
        self.manager.revoke_all("ai.openai")
        keys = self.manager.get_granted_keys("ai.openai")
        self.assertEqual(keys, [])

    # 13. has_grant が正しく判定する
    def test_13_has_grant(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A"])
        self.assertTrue(self.manager.has_grant("ai.openai", "KEY_A"))
        self.assertFalse(self.manager.has_grant("ai.openai", "KEY_B"))
        self.assertFalse(self.manager.has_grant("ai.unknown", "KEY_A"))

    # 14. get_granted_secrets が復号済み値を返す（SecretsStore モック）
    def test_14_get_granted_secrets_returns_values(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A", "KEY_B"])

        mock_store = MagicMock()
        mock_store._internal_read_value.side_effect = lambda k, caller_id="": {
            "KEY_A": "secret_value_a",
            "KEY_B": "secret_value_b",
        }.get(k)

        with patch(
            "core_runtime.secrets_grant_manager.get_secrets_store",
            return_value=mock_store,
        ):
            result = self.manager.get_granted_secrets("ai.openai")

        self.assertEqual(result, {"KEY_A": "secret_value_a", "KEY_B": "secret_value_b"})

    # 15. get_granted_secrets で存在しない Secret キーがスキップされる
    def test_15_get_granted_secrets_skips_missing(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A", "KEY_MISSING"])

        mock_store = MagicMock()
        mock_store._internal_read_value.side_effect = lambda k, caller_id="": {
            "KEY_A": "value_a",
        }.get(k)  # KEY_MISSING は None を返す

        with patch(
            "core_runtime.secrets_grant_manager.get_secrets_store",
            return_value=mock_store,
        ):
            result = self.manager.get_granted_secrets("ai.openai")

        self.assertEqual(result, {"KEY_A": "value_a"})
        self.assertNotIn("KEY_MISSING", result)

    # 16. HMAC 署名が不正な Grant ファイルが拒否される
    def test_16_tampered_hmac_rejected(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A"])
        grant_file = self.manager._get_grant_file("ai.openai")

        # ファイルを改ざん
        with open(grant_file, "r") as f:
            data = json.load(f)
        data["granted_keys"] = ["KEY_A", "KEY_INJECTED"]
        with open(grant_file, "w") as f:
            json.dump(data, f)

        # 新しいマネージャーでリロード
        from core_runtime.secrets_grant_manager import SecretsGrantManager
        manager2 = SecretsGrantManager(
            grants_dir=self._grants_dir,
            secret_key=self._secret_key,
        )
        # 改ざんされた Grant はロードされない
        keys = manager2.get_granted_keys("ai.openai")
        self.assertEqual(keys, [])

    # 17. delete_grant で Grant ファイルが削除される
    def test_17_delete_grant(self):
        self.manager.grant_secret_access("ai.openai", ["KEY_A"])
        grant_file = self.manager._get_grant_file("ai.openai")
        self.assertTrue(grant_file.exists())

        result = self.manager.delete_grant("ai.openai")
        self.assertTrue(result)
        self.assertFalse(grant_file.exists())
        self.assertEqual(self.manager.get_granted_keys("ai.openai"), [])


# ===========================================================================
# Test: 承認フロー (18-20)
# ===========================================================================


class TestApprovalFlowIntegration(unittest.TestCase):
    """approval_manager の承認フロー連携テスト"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="test_approval_")
        self._packs_dir = os.path.join(self._tmpdir, "ecosystem")
        self._grants_dir = os.path.join(self._tmpdir, "grants")
        os.makedirs(self._packs_dir, exist_ok=True)
        os.makedirs(self._grants_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_pack(self, pack_id: str, eco_data: dict):
        """テスト用 Pack ディレクトリと ecosystem.json を作成"""
        pack_dir = os.path.join(self._packs_dir, pack_id)
        os.makedirs(pack_dir, exist_ok=True)
        eco_path = os.path.join(pack_dir, "ecosystem.json")
        with open(eco_path, "w") as f:
            json.dump(eco_data, f)
        return pack_dir

    # 18. approve() の返り値に resource_requirements が含まれる
    def test_18_approve_returns_resource_requirements(self):
        eco_data = {
            "pack_id": "ai.openai",
            "required_secrets": ["OPENAI_API_KEY"],
            "required_network": {
                "allowed_domains": ["api.openai.com"],
                "allowed_ports": [443],
            },
        }
        self._create_pack("ai.openai", eco_data)

        from core_runtime.approval_manager import ApprovalManager
        am = ApprovalManager(
            packs_dir=self._packs_dir,
            grants_dir=self._grants_dir,
        )
        am.initialize()
        am.scan_packs()

        result = am.approve("ai.openai")
        self.assertTrue(result.success)

        # get_resource_requirements でリソース情報を取得
        rr = am.get_resource_requirements("ai.openai")
        self.assertIn("required_secrets", rr)
        self.assertEqual(rr["required_secrets"], ["OPENAI_API_KEY"])
        self.assertIn("required_network", rr)

    # 19. host_execution=true の Pack 承認時に警告ログが出る
    def test_19_host_execution_warning(self):
        eco_data = {
            "pack_id": "io.http.server",
            "host_execution": True,
        }
        self._create_pack("io.http.server", eco_data)

        from core_runtime.approval_manager import ApprovalManager
        am = ApprovalManager(
            packs_dir=self._packs_dir,
            grants_dir=self._grants_dir,
        )
        am.initialize()
        am.scan_packs()

        with self.assertLogs(level="WARNING") as cm:
            result = am.approve("io.http.server")

        self.assertTrue(result.success)
        # 警告ログに host_execution 関連のメッセージが含まれる
        warning_found = any("host_execution" in msg for msg in cm.output)
        self.assertTrue(
            warning_found,
            f"Expected host_execution warning in logs, got: {cm.output}",
        )

    # 20. required_secrets が空の Pack は resource_requirements が空
    def test_20_no_resource_requirements(self):
        eco_data = {
            "pack_id": "ai.basic",
        }
        self._create_pack("ai.basic", eco_data)

        from core_runtime.approval_manager import ApprovalManager
        am = ApprovalManager(
            packs_dir=self._packs_dir,
            grants_dir=self._grants_dir,
        )
        am.initialize()
        am.scan_packs()

        result = am.approve("ai.basic")
        self.assertTrue(result.success)

        rr = am.get_resource_requirements("ai.basic")
        self.assertEqual(rr, {})


# ===========================================================================
# Test: API (21-22)
# ===========================================================================


class TestSecretsGrantAPI(unittest.TestCase):
    """secrets_handlers の Grant API テスト"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="test_api_")
        self._grants_dir = os.path.join(self._tmpdir, "grants")
        self._secret_key = "b" * 64

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_handler(self):
        """テスト用ハンドラインスタンスを作成"""
        from core_runtime.secrets_grant_manager import SecretsGrantManager

        mgr = SecretsGrantManager(
            grants_dir=self._grants_dir,
            secret_key=self._secret_key,
        )

        from core_runtime.api.secrets_handlers import SecretsHandlersMixin

        class TestHandler(SecretsHandlersMixin):
            pass

        handler = TestHandler()
        return handler, mgr

    # 21. _secrets_grant が正常に Grant を作成する
    def test_21_secrets_grant_api(self):
        handler, mgr = self._make_handler()

        with patch(
            "core_runtime.api.secrets_handlers._get_secrets_grant_manager",
            return_value=mgr,
        ):
            result = handler._secrets_grant({
                "pack_id": "ai.openai",
                "secret_keys": ["OPENAI_API_KEY"],
            })

        self.assertTrue(result.get("success"))
        keys = mgr.get_granted_keys("ai.openai")
        self.assertIn("OPENAI_API_KEY", keys)

    # 22. _secrets_revoke_grant が正常に Revoke する
    def test_22_secrets_revoke_grant_api(self):
        handler, mgr = self._make_handler()
        mgr.grant_secret_access("ai.openai", ["KEY_A", "KEY_B"])

        with patch(
            "core_runtime.api.secrets_handlers._get_secrets_grant_manager",
            return_value=mgr,
        ):
            result = handler._secrets_revoke_grant({
                "pack_id": "ai.openai",
                "secret_keys": ["KEY_A"],
            })

        self.assertTrue(result.get("success"))
        keys = mgr.get_granted_keys("ai.openai")
        self.assertNotIn("KEY_A", keys)
        self.assertIn("KEY_B", keys)


if __name__ == "__main__":
    unittest.main()
