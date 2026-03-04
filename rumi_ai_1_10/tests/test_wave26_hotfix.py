"""
W26-HOTFIX: 起動フロー修正 + Approval Manager バグ修正 テスト

テスト観点:
1. _read_ecosystem_data() メソッド定義が存在すること
2. _read_ecosystem_data() が ecosystem.json を読めること
3. _read_ecosystem_data() が存在しない pack に空 dict を返すこと
4. approve() が AttributeError なしで完了すること
5. host_execution=true の pack でも approve() が成功すること
6. DI コンテナから取得した ApprovalManager が initialize() 済みであること
7. 承認 → 再ロードで APPROVED 状態が維持されること
8. HMAC 署名の生成と検証が一貫すること
9. FlowConverter が startup flow を正しく変換すること
10. scan_packs → approve → verify_hash の一連フローが動くこと
11. reset 後の再取得で initialize() 済みインスタンスが返ること
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# テスト用に RUMI_SECURITY_MODE=permissive を設定
os.environ["RUMI_SECURITY_MODE"] = "permissive"

# sys.path にプロジェクトルートを追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    """各テスト前に DI コンテナと一時ディレクトリをリセット"""
    from core_runtime.di_container import reset_container
    reset_container()

    user_data = tmp_path / "user_data"
    user_data.mkdir()
    permissions_dir = user_data / "permissions"
    permissions_dir.mkdir()

    yield {
        "tmp_path": tmp_path,
        "user_data": user_data,
        "permissions_dir": permissions_dir,
    }

    reset_container()


def _make_pack(tmp_path, pack_id="test_pack", extra_fields=None):
    """テスト用 Pack を作成"""
    ecosystem_dir = tmp_path / "ecosystem"
    ecosystem_dir.mkdir(exist_ok=True)
    pack_dir = ecosystem_dir / pack_id
    pack_dir.mkdir(exist_ok=True)
    eco_data = {
        "pack_id": pack_id,
        "pack_identity": f"com.test.{pack_id}",
        "version": "1.0.0",
        "components": [],
    }
    if extra_fields:
        eco_data.update(extra_fields)
    eco_json = pack_dir / "ecosystem.json"
    eco_json.write_text(json.dumps(eco_data), encoding="utf-8")
    return ecosystem_dir, pack_dir


# ============================================================
# Test 1: _read_ecosystem_data() メソッド定義が存在すること
# ============================================================
def test_read_ecosystem_data_method_exists(clean_env):
    from core_runtime.approval_manager import ApprovalManager
    am = ApprovalManager(
        packs_dir=str(clean_env["tmp_path"] / "ecosystem"),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    assert hasattr(am, "_read_ecosystem_data"), \
        "_read_ecosystem_data method must exist on ApprovalManager"
    assert callable(am._read_ecosystem_data)


# ============================================================
# Test 2: _read_ecosystem_data() が ecosystem.json を読めること
# ============================================================
def test_read_ecosystem_data_reads_json(clean_env):
    ecosystem_dir, pack_dir = _make_pack(clean_env["tmp_path"], "mypack")

    from core_runtime.approval_manager import ApprovalManager
    am = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()
    am.scan_packs()

    data = am._read_ecosystem_data("mypack")
    assert isinstance(data, dict)
    assert data.get("pack_id") == "mypack"


# ============================================================
# Test 3: _read_ecosystem_data() が存在しない pack に空 dict を返すこと
# ============================================================
def test_read_ecosystem_data_missing_pack(clean_env):
    from core_runtime.approval_manager import ApprovalManager
    am = ApprovalManager(
        packs_dir=str(clean_env["tmp_path"] / "ecosystem"),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()

    data = am._read_ecosystem_data("nonexistent_pack")
    assert data == {}


# ============================================================
# Test 4: approve() が AttributeError なしで完了すること
# ============================================================
def test_approve_no_attribute_error(clean_env):
    ecosystem_dir, pack_dir = _make_pack(clean_env["tmp_path"], "approvetest")

    from core_runtime.approval_manager import ApprovalManager
    am = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()
    am.scan_packs()

    result = am.approve("approvetest")
    assert result.success is True, f"approve() failed: {result.error}"


# ============================================================
# Test 5: approve() が host_execution=true の pack でも成功すること
# ============================================================
def test_approve_host_execution_pack(clean_env):
    ecosystem_dir, pack_dir = _make_pack(
        clean_env["tmp_path"], "hostexec",
        extra_fields={"host_execution": True},
    )

    from core_runtime.approval_manager import ApprovalManager
    am = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()
    am.scan_packs()

    result = am.approve("hostexec")
    assert result.success is True, f"approve() failed for host_execution pack: {result.error}"


# ============================================================
# Test 6: DI コンテナから取得した ApprovalManager が initialize() 済みであること
# ============================================================
def test_di_container_approval_manager_initialized(clean_env):
    from core_runtime.di_container import get_container
    container = get_container()
    am = container.get("approval_manager")
    assert am._initialized is True, "ApprovalManager from DI must be initialized"


# ============================================================
# Test 7: 承認 → 再ロードで APPROVED 状態が維持されること
# ============================================================
def test_approve_persists_across_reload(clean_env):
    ecosystem_dir, pack_dir = _make_pack(clean_env["tmp_path"], "persist_test")

    from core_runtime.approval_manager import ApprovalManager, PackStatus
    am1 = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am1.initialize()
    am1.scan_packs()
    result = am1.approve("persist_test")
    assert result.success is True

    # 新しいインスタンスで再ロード
    am2 = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am2.initialize()
    status = am2.get_status("persist_test")
    assert status == PackStatus.APPROVED, f"Expected APPROVED, got {status}"


# ============================================================
# Test 8: HMAC 署名の生成と検証が一貫すること
# ============================================================
def test_hmac_signature_consistency(clean_env):
    ecosystem_dir, pack_dir = _make_pack(clean_env["tmp_path"], "hmac_test")

    from core_runtime.approval_manager import ApprovalManager, PackStatus
    am = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()
    am.scan_packs()
    am.approve("hmac_test")

    # grants.json が書き出されていること
    grant_file = clean_env["permissions_dir"] / "hmac_test.grants.json"
    assert grant_file.exists(), "Grant file must be written"

    # 再ロードで HMAC 検証が成功すること（MODIFIED にならない）
    am2 = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am2.initialize()
    status = am2.get_status("hmac_test")
    assert status == PackStatus.APPROVED, f"HMAC verification failed, status={status}"


# ============================================================
# Test 9: FlowConverter が startup flow を正しく変換すること
# ============================================================
def test_flow_converter_startup(clean_env):
    from core_runtime.kernel_flow_converter import FlowConverter

    converter = FlowConverter()
    flow_def = {
        "flow_id": "startup",
        "phases": ["init", "security"],
        "defaults": {"fail_soft": True},
        "steps": [
            {
                "id": "mounts_init",
                "phase": "init",
                "priority": 10,
                "type": "handler",
                "input": {
                    "handler": "kernel:mounts.init",
                    "args": {"mounts_file": "user_data/mounts.json"},
                },
            },
            {
                "id": "api_init",
                "phase": "security",
                "priority": 40,
                "type": "handler",
                "input": {
                    "handler": "kernel:api.init",
                    "args": {"host": "127.0.0.1", "port": 8765},
                },
            },
        ],
    }

    result = converter.convert_new_flow_to_pipelines(flow_def)
    assert "pipelines" in result
    startup_steps = result["pipelines"]["startup"]
    assert len(startup_steps) == 2

    s1 = startup_steps[0]
    assert s1["id"] == "mounts_init"
    assert s1["run"]["handler"] == "kernel:mounts.init"

    s2 = startup_steps[1]
    assert s2["id"] == "api_init"
    assert s2["run"]["handler"] == "kernel:api.init"
    assert s2["run"]["args"]["port"] == 8765


# ============================================================
# Test 10: scan_packs → approve → verify_hash の一連フロー
# ============================================================
def test_scan_approve_verify_flow(clean_env):
    ecosystem_dir, pack_dir = _make_pack(clean_env["tmp_path"], "flow_test")

    from core_runtime.approval_manager import ApprovalManager, PackStatus
    am = ApprovalManager(
        packs_dir=str(ecosystem_dir),
        grants_dir=str(clean_env["permissions_dir"]),
    )
    am.initialize()

    packs = am.scan_packs()
    assert "flow_test" in packs

    result = am.approve("flow_test")
    assert result.success is True
    assert result.status == PackStatus.APPROVED

    assert am.verify_hash("flow_test") is True

    # ファイルを変更
    new_file = pack_dir / "new_file.txt"
    new_file.write_text("modified", encoding="utf-8")

    assert am.verify_hash("flow_test", use_cache=False) is False


# ============================================================
# Test 11: reset 後の再取得で initialize() 済みインスタンスが返ること
# ============================================================
def test_di_reset_returns_initialized(clean_env):
    from core_runtime.di_container import get_container

    container = get_container()

    am1 = container.get("approval_manager")
    assert am1._initialized is True

    container.reset("approval_manager")

    am2 = container.get("approval_manager")
    assert am2._initialized is True
    assert am2 is not am1
