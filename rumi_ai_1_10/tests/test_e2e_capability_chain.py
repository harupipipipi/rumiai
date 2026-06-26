"""
test_e2e_capability_chain.py - Capability Trust → Grant → Execute E2E テスト

テスト観点:
- Pack が Capability を宣言 → Trust 付与 → Grant → 実行成功
- Trust 未付与の Pack が Capability を実行 → 拒否
- Grant のない Capability を実行 → 拒否
- Trust + Grant 付与済みだが、ネットワークアクセスが制限されている場合
- 改ざんされた Grant ファイルの拒否
- built-in ハンドラの Trust バイパス
- cwd が違っても Grant の HMAC 検証が tamper 誤検知しないこと

既存の test_capability_system.py / test_secure_execution.py の書き方に合わせる。
"""

from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# テスト対象をインポートできるようにパスを追加
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
from core_runtime.capability_trust_store import (
    CapabilityTrustStore,
    TrustCheckResult,
)
from core_runtime.capability_grant_manager import (
    CapabilityGrantManager,
    GrantCheckResult,
)
from core_runtime.function_registry import FunctionEntry, FunctionRegistry


def _compute_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sanitize_principal_id(principal_id: str) -> str:
    """principal_id をファイルシステム安全な文字列に変換"""
    return re.sub(r'[/\\:*?"<>|.\x00-\x1f]', "_", principal_id)


def _compute_hmac(secret_key: str, data: dict) -> str:
    """HMAC-SHA256 署名を計算"""
    data_copy = {k: v for k, v in data.items() if not k.startswith("_hmac")}
    payload = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
    return hmac_module.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _compute_trust_hmac(trust_dir: Path, data: dict) -> str:
    """TrustStore と同じ鍵でテスト用 trust file に署名する。"""
    from core_runtime.hmac_key_manager import (
        compute_data_hmac,
        generate_or_load_signing_key,
    )

    key = generate_or_load_signing_key(
        trust_dir / ".secret_key",
        env_var="RUMI_HMAC_SECRET",
    )
    return compute_data_hmac(key, data)


# =========================================================================
# E2E: Trust → Grant → Execute チェーンテスト
# =========================================================================


class TestCapabilityChainE2E(unittest.TestCase):
    """Capability セキュリティチェーンの E2E テスト"""

    def setUp(self):
        """テスト環境の準備"""
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_cap_chain_")
        self.handlers_dir = Path(self.tmpdir) / "handlers"
        self.trust_dir = Path(self.tmpdir) / "trust"
        self.grants_dir = Path(self.tmpdir) / "grants"

        self.handlers_dir.mkdir(parents=True)
        self.trust_dir.mkdir(parents=True)
        self.grants_dir.mkdir(parents=True)

        # secret key（Grant の HMAC 署名に必要）
        self.secret_key = hashlib.sha256(b"test_secret_e2e").hexdigest()
        self.function_entries: list[FunctionEntry] = []

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_function(
        self,
        slug,
        function_id,
        permission_id,
        code=None,
        *,
        pack_id="test_pack",
        grant_config=None,
    ):
        """テスト用 function を作成し、FunctionRegistry 登録用 entry と sha256 を返す。"""
        d = self.handlers_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        if code is None:
            code = 'def execute(context, args): return {"echo": args}\n'
        handler_py = d / "handler.py"
        handler_py.write_text(code, encoding="utf-8")
        sha = _compute_sha256(handler_py)
        entry = FunctionEntry(
            function_id=function_id,
            pack_id=pack_id,
            description=f"Test function for {permission_id}",
            function_dir=d,
            main_py_path=handler_py,
            entrypoint="handler.py:execute",
            grant_config={} if grant_config is None else grant_config,
            vocab_aliases=[permission_id],
            permission_id=permission_id,
            calling_convention="subprocess",
        )
        self.function_entries.append(entry)
        return entry, sha

    def _setup_trust(self, handler_id, sha256):
        """Trust ストアにハンドラを信頼として追加"""
        trust_file = self.trust_dir / "trusted_handlers.json"
        data = {"version": "1.0", "trusted": []}

        if trust_file.exists():
            with open(trust_file, "r", encoding="utf-8") as f:
                data = json.load(f)

        data["trusted"].append({
            "handler_id": handler_id,
            "sha256": sha256,
            "note": "test trust",
        })
        data["_hmac_signature"] = _compute_trust_hmac(self.trust_dir, data)

        with open(trust_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _setup_grant(self, principal_id, permission_id, enabled=True, config=None):
        """Grant を作成（HMAC 署名付き）"""
        grant_data = {
            "version": "1.0",
            "principal_id": principal_id,
            "enabled": True,
            "granted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "permissions": {
                permission_id: {
                    "enabled": enabled,
                    "config": config or {},
                },
            },
        }

        grant_data["_hmac_signature"] = _compute_hmac(self.secret_key, grant_data)

        safe_id = _sanitize_principal_id(principal_id)
        grant_file = self.grants_dir / f"{safe_id}.json"
        with open(grant_file, "w", encoding="utf-8") as f:
            json.dump(grant_data, f, ensure_ascii=False, indent=2)

    def _build_executor(self):
        """テスト用 CapabilityExecutor を構築"""
        registry = FunctionRegistry()
        for entry in self.function_entries:
            registry.register(entry)

        trust_store = CapabilityTrustStore(str(self.trust_dir))
        trust_store.load()

        grant_manager = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )

        executor = CapabilityExecutor()
        executor._initialized = True
        executor._function_registry = registry
        executor._handler_registry = None
        executor._trust_store = trust_store
        executor._grant_manager = grant_manager
        return executor, registry, trust_store, grant_manager

    # -----------------------------------------------------------------
    # E2E テストケース
    # -----------------------------------------------------------------

    def test_full_chain_trust_grant_execute_success(self):
        """E2E: Trust 付与 → Grant 付与 → 実行成功"""
        handler_id = "test.echo.v1"
        permission_id = "test.echo"
        principal_id = "pack_alpha"

        entry, sha = self._create_function("echo", handler_id, permission_id)
        self._setup_trust(entry.qualified_name, sha)
        self._setup_grant(principal_id, permission_id)

        executor, *_ = self._build_executor()

        mock_resp = CapabilityResponse(
            success=True,
            output={"echo": {"test": "data"}},
            latency_ms=10.0,
        )
        with patch.object(executor, '_execute_handler_subprocess', return_value=mock_resp):
            resp = executor.execute(
                principal_id=principal_id,
                request={"permission_id": permission_id, "args": {"test": "data"}},
            )

        self.assertTrue(resp.success, f"Expected success but got error: {resp.error}")

    def test_untrusted_handler_denied(self):
        """E2E: Trust 未付与 → 実行拒否（trust_denied）"""
        handler_id = "untrusted.handler.v1"
        permission_id = "untrusted.action"
        principal_id = "pack_beta"

        # Trust は付与しない
        self._create_function("untrusted", handler_id, permission_id)
        self._setup_grant(principal_id, permission_id)

        executor, *_ = self._build_executor()

        resp = executor.execute(
            principal_id=principal_id,
            request={"permission_id": permission_id, "args": {}},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "trust_denied")
        self.assertEqual(resp.error, "Permission denied")

    def test_no_grant_denied(self):
        """E2E: Trust 付与済みだが Grant なし → 実行拒否（grant_denied）"""
        handler_id = "granted.handler.v1"
        permission_id = "granted.action"
        principal_id = "pack_gamma"

        entry, sha = self._create_function("no_grant", handler_id, permission_id)
        self._setup_trust(entry.qualified_name, sha)
        # Grant は付与しない

        executor, *_ = self._build_executor()

        resp = executor.execute(
            principal_id=principal_id,
            request={"permission_id": permission_id, "args": {}},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "grant_denied")
        self.assertEqual(resp.error, "Permission denied")

    def test_trust_and_grant_with_network_restriction_config(self):
        """E2E: Trust + Grant 済みだがネットワーク制限 config 付き

        Grant の config に allowed_domains=[] / allowed_ports=[] を設定。
        ea50dfd の security fix 後、空リスト = 全拒否。
        Grant チェック自体は通るが、config にネットワーク制限が含まれる。
        """
        handler_id = "net.handler.v1"
        permission_id = "net.request"
        principal_id = "pack_delta"

        entry, sha = self._create_function("net_handler", handler_id, permission_id)
        self._setup_trust(entry.qualified_name, sha)
        self._setup_grant(
            principal_id,
            permission_id,
            enabled=True,
            config={
                "allowed_domains": [],  # 空リスト = 全拒否（security fix 後）
                "allowed_ports": [],    # 空リスト = 全拒否（security fix 後）
            },
        )

        _, _, _, grant_manager = self._build_executor()

        # Grant チェック自体は成功する（Grant は存在する）
        grant_result = grant_manager.check(principal_id, permission_id)
        self.assertTrue(grant_result.allowed)

        # config にネットワーク制限が含まれていることを確認
        self.assertEqual(grant_result.config.get("allowed_domains"), [])
        self.assertEqual(grant_result.config.get("allowed_ports"), [])

        # NetworkGrantManager の _check_domain で空リスト = False を確認
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        # _check_domain / _check_port は pure function に近いので直接テスト
        self.assertFalse(ngm._check_domain("example.com", []))
        self.assertFalse(ngm._check_port(443, []))
        # ワイルドカード指定なら許可
        self.assertTrue(ngm._check_domain("example.com", ["*"]))
        self.assertTrue(ngm._check_port(443, [0]))

    def test_handler_not_found(self):
        """存在しない permission_id での実行 → handler_not_found"""
        executor, *_ = self._build_executor()

        resp = executor.execute(
            principal_id="any_pack",
            request={"permission_id": "nonexistent.permission", "args": {}},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "handler_not_found")

    def test_missing_permission_id_rejected(self):
        """permission_id がないリクエスト → invalid_request"""
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._handler_registry = MagicMock()
        executor._trust_store = MagicMock()
        executor._grant_manager = MagicMock()

        resp = executor.execute(
            principal_id="any_pack",
            request={"args": {}},  # permission_id なし
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "invalid_request")

    def test_builtin_handler_bypasses_trust(self):
        """built-in ハンドラは Trust チェックをバイパスする"""
        handler_id = "builtin.echo.v1"
        permission_id = "builtin.echo"
        principal_id = "pack_epsilon"

        # Trust は付与しない（built-in はバイパスするため不要）
        entry, _ = self._create_function(
            "builtin_echo",
            handler_id,
            permission_id,
            pack_id="core_legacy",
        )
        entry.legacy_handler_builtin = True
        self._setup_grant(principal_id, permission_id)

        executor, registry, _, _ = self._build_executor()

        entry = registry.get_by_permission_id(permission_id)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.pack_id.startswith("core_"))

        mock_resp = CapabilityResponse(
            success=True,
            output={"builtin": "result"},
            latency_ms=5.0,
        )
        with patch.object(executor, '_execute_handler_subprocess', return_value=mock_resp):
            resp = executor.execute(
                principal_id=principal_id,
                request={"permission_id": permission_id, "args": {}},
            )

        self.assertTrue(resp.success, f"Expected success but got: {resp.error}")

    def test_tampered_grant_file_rejected(self):
        """改ざんされた Grant ファイルは拒否される"""
        handler_id = "tamper.handler.v1"
        permission_id = "tamper.action"
        principal_id = "pack_zeta"

        entry, sha = self._create_function("tamper", handler_id, permission_id)
        self._setup_trust(entry.qualified_name, sha)
        self._setup_grant(principal_id, permission_id)

        # Grant ファイルを改ざん（ペイロードを変えて HMAC を壊す）
        safe_id = _sanitize_principal_id(principal_id)
        grant_file = self.grants_dir / f"{safe_id}.json"
        with open(grant_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["permissions"]["tamper.extra"] = {"enabled": True, "config": {}}
        with open(grant_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # GrantManager を再読み込み
        grant_manager = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )

        # 改ざん検知で拒否
        result = grant_manager.check(principal_id, permission_id)
        self.assertFalse(result.allowed)
        self.assertIn("tampered", result.reason.lower())

    def test_disabled_grant_rejected(self):
        """enabled=False の Grant は拒否"""
        handler_id = "disabled.handler.v1"
        permission_id = "disabled.action"
        principal_id = "pack_eta"

        entry, sha = self._create_function("disabled", handler_id, permission_id)
        self._setup_trust(entry.qualified_name, sha)
        self._setup_grant(principal_id, permission_id, enabled=False)

        executor, *_ = self._build_executor()

        resp = executor.execute(
            principal_id=principal_id,
            request={"permission_id": permission_id, "args": {}},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "grant_denied")

    def test_grant_reload_from_same_path_different_cwd_no_false_tamper(self):
        """cwd が違っても同一パスの Grant は tamper 誤検知しない回帰テスト。

        CapabilityGrantManager が cwd に依存しないパス解決 (_PROJECT_ROOT) を
        使用していることを確認する。
        """
        principal_id = "cwd_test_pack"
        permission_id = "cwd.test.perm"

        # 1. Grant を HMAC 署名付きで作成
        self._setup_grant(principal_id, permission_id)

        # 2. 同じパス + 同じ secret_key で CapabilityGrantManager を2回構築
        #    (1回目: 現在の cwd、2回目: 異なる cwd に変更してから)
        gm1 = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )
        result1 = gm1.check(principal_id, permission_id)
        self.assertTrue(result1.allowed, f"First load should allow: {result1.reason}")

        # cwd を変更してから再度同じパスで構築
        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)  # tmpdir を cwd に変更
            gm2 = CapabilityGrantManager(
                grants_dir=str(self.grants_dir),
                secret_key=self.secret_key,
            )
            result2 = gm2.check(principal_id, permission_id)
            self.assertTrue(result2.allowed, f"Reload after cwd change should allow: {result2.reason}")
        finally:
            os.chdir(original_cwd)


# =========================================================================
# Trust Store 基盤テスト
# =========================================================================


class TestTrustStoreBasics(unittest.TestCase):
    """CapabilityTrustStore の基本動作テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_trust_")
        self.trust_dir = Path(self.tmpdir) / "trust"
        self.trust_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_trust_store_denies_all(self):
        """空の Trust ストアは全てのハンドラを拒否"""
        store = CapabilityTrustStore(str(self.trust_dir))
        store.load()
        result = store.is_trusted("any.handler", "a" * 64)
        self.assertFalse(result.trusted)
        self.assertIn("not in trust list", result.reason)

    def test_add_and_check_trust(self):
        """Trust 追加後のチェック"""
        store = CapabilityTrustStore(str(self.trust_dir))
        store.load()
        sha = "a" * 64
        store.add_trust("test.handler.v1", sha, "test note")
        result = store.is_trusted("test.handler.v1", sha)
        self.assertTrue(result.trusted)

    def test_sha256_mismatch_denied(self):
        """SHA-256 不一致で拒否"""
        store = CapabilityTrustStore(str(self.trust_dir))
        store.load()
        store.add_trust("test.handler.v1", "a" * 64)
        result = store.is_trusted("test.handler.v1", "b" * 64)
        self.assertFalse(result.trusted)
        self.assertIn("mismatch", result.reason.lower())

    def test_unloaded_store_denies(self):
        """未ロードの Trust ストアは全拒否"""
        store = CapabilityTrustStore(str(self.trust_dir))
        # load() を呼ばない
        result = store.is_trusted("any.handler", "a" * 64)
        self.assertFalse(result.trusted)
        self.assertIn("not loaded", result.reason.lower())

    def test_remove_trust(self):
        """Trust 削除後は拒否"""
        store = CapabilityTrustStore(str(self.trust_dir))
        store.load()
        sha = "c" * 64
        store.add_trust("removable.v1", sha)
        store.remove_trust("removable.v1")
        result = store.is_trusted("removable.v1", sha)
        self.assertFalse(result.trusted)


# =========================================================================
# Grant Manager 基盤テスト
# =========================================================================


class TestGrantManagerBasics(unittest.TestCase):
    """CapabilityGrantManager の基本動作テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_grant_")
        self.grants_dir = Path(self.tmpdir) / "grants"
        self.grants_dir.mkdir(parents=True)
        self.secret_key = hashlib.sha256(b"test_secret_grant").hexdigest()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_grant_denied(self):
        """Grant なしは拒否"""
        gm = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )
        result = gm.check("unknown_principal", "some.permission")
        self.assertFalse(result.allowed)

    def test_valid_grant_allows(self):
        """有効な Grant で実行許可"""
        principal_id = "test_pack"
        permission_id = "test.read"

        grant_data = {
            "version": "1.0",
            "principal_id": principal_id,
            "enabled": True,
            "granted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "permissions": {
                permission_id: {"enabled": True, "config": {}},
            },
        }
        grant_data["_hmac_signature"] = _compute_hmac(self.secret_key, grant_data)

        grant_file = self.grants_dir / f"{principal_id}.json"
        with open(grant_file, "w", encoding="utf-8") as f:
            json.dump(grant_data, f, ensure_ascii=False, indent=2)

        gm = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )
        result = gm.check(principal_id, permission_id)
        self.assertTrue(result.allowed)

    def test_unsigned_grant_rejected(self):
        """署名なしの Grant ファイルは拒否"""
        principal_id = "unsigned_pack"
        permission_id = "some.perm"

        grant_data = {
            "version": "1.0",
            "principal_id": principal_id,
            "enabled": True,
            "granted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "permissions": {
                permission_id: {"enabled": True, "config": {}},
            },
            # _hmac_signature なし
        }

        grant_file = self.grants_dir / f"{principal_id}.json"
        with open(grant_file, "w", encoding="utf-8") as f:
            json.dump(grant_data, f, ensure_ascii=False, indent=2)

        gm = CapabilityGrantManager(
            grants_dir=str(self.grants_dir),
            secret_key=self.secret_key,
        )
        result = gm.check(principal_id, permission_id)
        self.assertFalse(result.allowed)
        self.assertIn("tampered", result.reason.lower())


# =========================================================================
# NetworkGrantManager セキュリティ修正テスト
# =========================================================================


class TestNetworkGrantManagerSecurityFix(unittest.TestCase):
    """ea50dfd の空リスト=全拒否修正のテスト"""

    def test_empty_domain_list_denies_all(self):
        """allowed_domains=[] → 全拒否"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertFalse(ngm._check_domain("example.com", []))
        self.assertFalse(ngm._check_domain("localhost", []))

    def test_wildcard_domain_allows_all(self):
        """allowed_domains=["*"] → 全許可"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertTrue(ngm._check_domain("example.com", ["*"]))
        self.assertTrue(ngm._check_domain("anything.test", ["*"]))

    def test_empty_port_list_denies_all(self):
        """allowed_ports=[] → 全拒否"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertFalse(ngm._check_port(80, []))
        self.assertFalse(ngm._check_port(443, []))

    def test_wildcard_port_allows_all(self):
        """allowed_ports=[0] → 全許可"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertTrue(ngm._check_port(80, [0]))
        self.assertTrue(ngm._check_port(443, [0]))

    def test_specific_domain_match(self):
        """特定ドメインの完全一致"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertTrue(ngm._check_domain("api.example.com", ["api.example.com"]))
        self.assertFalse(ngm._check_domain("other.com", ["api.example.com"]))

    def test_specific_port_match(self):
        """特定ポートの一致"""
        from core_runtime.network_grant_manager import NetworkGrantManager
        ngm = NetworkGrantManager.__new__(NetworkGrantManager)
        self.assertTrue(ngm._check_port(443, [80, 443]))
        self.assertFalse(ngm._check_port(8080, [80, 443]))


if __name__ == "__main__":
    unittest.main()
