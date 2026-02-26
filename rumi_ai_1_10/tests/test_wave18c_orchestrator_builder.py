"""
test_wave18c_orchestrator_builder.py

W18-C: ContainerOrchestrator の DockerRunBuilder 移行テスト（14ケース）
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# テスト用に core_runtime パッケージのインポートパスを解決
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_paths(monkeypatch, tmp_path):
    """ECOSYSTEM_DIR をテンポラリに差し替え"""
    monkeypatch.setattr(
        "core_runtime.container_orchestrator.ECOSYSTEM_DIR",
        str(tmp_path / "ecosystem"),
    )


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _make_orchestrator():
    """パッチ済み ContainerOrchestrator を生成"""
    from core_runtime.container_orchestrator import ContainerOrchestrator
    orch = ContainerOrchestrator()
    orch._docker_available = True  # Docker 利用可能を強制
    return orch


def _capture_docker_run_cmd(
    orch,
    pack_id: str = "testpack",
    *,
    existing_container: bool = False,
    egress_sock: Optional[Path] = None,
    egress_ok: bool = True,
    cap_sock: Optional[Path] = None,
    cap_ok: bool = True,
    egress_raise: bool = False,
    cap_raise: bool = False,
) -> List[str]:
    """
    start_container を呼び出し、subprocess.run に渡された docker run コマンドを返す。

    existing_container=True の場合は docker ps が既存IDを返す（docker start パス）。
    """
    captured_cmds: List[List[str]] = []

    def _fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        result = mock.MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""

        # docker ps チェック
        if cmd[0] == "docker" and cmd[1] == "ps":
            if existing_container:
                result.stdout = "abc123existing"
            else:
                result.stdout = ""
            return result

        # docker start
        if cmd[0] == "docker" and cmd[1] == "start":
            result.stdout = ""
            return result

        # docker run
        if cmd[0] == "docker" and cmd[1] == "run":
            result.stdout = "new_container_id_12345"
            return result

        return result

    # Egress モック
    mock_egress_mgr = mock.MagicMock()
    if egress_raise:
        mock_egress_mgr.ensure_pack_socket.side_effect = RuntimeError("egress down")
    else:
        mock_egress_mgr.ensure_pack_socket.return_value = (egress_ok, "", egress_sock)

    def _fake_get_egress():
        return mock_egress_mgr

    # Capability モック
    mock_cap_proxy = mock.MagicMock()
    if cap_raise:
        mock_cap_proxy.ensure_principal_socket.side_effect = RuntimeError("cap down")
    else:
        mock_cap_proxy.ensure_principal_socket.return_value = (cap_ok, None, cap_sock)

    def _fake_get_cap():
        return mock_cap_proxy

    with mock.patch("subprocess.run", side_effect=_fake_run):
        with mock.patch(
            "core_runtime.container_orchestrator.get_uds_egress_proxy_manager",
            _fake_get_egress,
            create=True,
        ):
            with mock.patch(
                "core_runtime.container_orchestrator.get_capability_proxy",
                _fake_get_cap,
                create=True,
            ):
                # egress_proxy / capability_proxy の import をモック
                with mock.patch.dict("sys.modules", {
                    "core_runtime.egress_proxy": mock.MagicMock(
                        get_uds_egress_proxy_manager=_fake_get_egress
                    ),
                    "core_runtime.capability_proxy": mock.MagicMock(
                        get_capability_proxy=_fake_get_cap
                    ),
                }):
                    orch.start_container(pack_id)

    # docker run コマンドを探す
    for cmd in captured_cmds:
        if len(cmd) >= 3 and cmd[0] == "docker" and cmd[1] == "run":
            return cmd

    # docker start パスの場合はコマンドリスト全体を返す
    return captured_cmds[-1] if captured_cmds else []


# ===========================================================================
# テストケース（14件）
# ===========================================================================


class TestOrchestratorUsesDockerRunBuilder:
    """Task 1: start_container が DockerRunBuilder を使ってコマンドを構築する"""

    def test_01_uses_docker_run_builder(self):
        """#1: DockerRunBuilder 由来のセキュリティベースラインが含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        # DockerRunBuilder のデフォルトが含まれていることで使用を確認
        assert "--cap-drop=ALL" in cmd
        assert "--security-opt=no-new-privileges:true" in cmd
        assert "--read-only" in cmd

    def test_02_has_detach_flag(self):
        """#2: 生成コマンドに -d が含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "-d" in cmd
        # -d は "docker" "run" の直後（index 2）にある
        assert cmd.index("-d") == 2

    def test_03_no_rm_flag(self):
        """#3: 生成コマンドに --rm が含まれない"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--rm" not in cmd

    def test_04_network_none(self):
        """#4: --network=none が含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--network=none" in cmd

    def test_05_cap_drop_all(self):
        """#5: --cap-drop=ALL が含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--cap-drop=ALL" in cmd

    def test_06_memory_256m(self):
        """#6: --memory=256m が含まれる（旧 128m ではない）"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--memory=256m" in cmd
        assert "--memory=128m" not in cmd
        assert "--memory-swap=256m" in cmd
        assert "--memory-swap=128m" not in cmd

    def test_07_pids_limit_50(self):
        """#7: --pids-limit=50 が含まれる（旧 100 ではない）"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--pids-limit=50" in cmd
        assert "--pids-limit=100" not in cmd

    def test_08_dns_127_0_0_1(self):
        """#8: --dns=127.0.0.1 が含まれる（旧実装では欠落）"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--dns=127.0.0.1" in cmd

    def test_09_label_pack_id(self):
        """#9: --label rumi.pack_id={pack_id} が含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch, pack_id="mypack42")
        assert "--label" in cmd
        label_idx = [i for i, c in enumerate(cmd) if c == "--label"]
        label_values = [cmd[i + 1] for i in label_idx if i + 1 < len(cmd)]
        assert "rumi.pack_id=mypack42" in label_values

    def test_10_label_managed(self):
        """#10: --label rumi.managed=true が含まれる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(orch)
        assert "--label" in cmd
        label_idx = [i for i, c in enumerate(cmd) if c == "--label"]
        label_values = [cmd[i + 1] for i in label_idx if i + 1 < len(cmd)]
        assert "rumi.managed=true" in label_values

    def test_11_existing_container_uses_docker_start(self):
        """#11: 既存コンテナがある場合は docker start が呼ばれる（DockerRunBuilder 不使用）"""
        orch = _make_orchestrator()

        captured_cmds: List[List[str]] = []

        def _fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            result = mock.MagicMock()
            result.returncode = 0
            result.stderr = ""
            if cmd[0] == "docker" and cmd[1] == "ps":
                result.stdout = "existing_container_abc"
            else:
                result.stdout = ""
            return result

        with mock.patch("subprocess.run", side_effect=_fake_run):
            orch.start_container("testpack")

        # docker start が呼ばれ、docker run は呼ばれない
        start_calls = [c for c in captured_cmds if c[:2] == ["docker", "start"]]
        run_calls = [c for c in captured_cmds if c[:2] == ["docker", "run"]]
        assert len(start_calls) == 1
        assert len(run_calls) == 0

    def test_12_egress_socket_mounted(self):
        """#12: Egress UDS ソケットがマウントされる"""
        orch = _make_orchestrator()
        egress_path = Path("/run/rumi/egress/packs/abc123.sock")
        cmd = _capture_docker_run_cmd(
            orch,
            egress_sock=egress_path,
            egress_ok=True,
        )
        # -v でソケットがマウントされている
        volume_args = []
        for i, c in enumerate(cmd):
            if c == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])
        egress_mounts = [v for v in volume_args if "egress.sock" in v]
        assert len(egress_mounts) == 1
        assert egress_mounts[0] == f"{egress_path}:/run/rumi/egress.sock:rw"

        # 環境変数も設定されている
        env_args = []
        for i, c in enumerate(cmd):
            if c == "-e" and i + 1 < len(cmd):
                env_args.append(cmd[i + 1])
        egress_env = [e for e in env_args if e.startswith("RUMI_EGRESS_SOCKET=")]
        assert len(egress_env) == 1

    def test_13_capability_socket_mounted(self):
        """#13: Capability UDS ソケットがマウントされる"""
        orch = _make_orchestrator()
        cap_path = Path("/run/rumi/capability/principals/def456.sock")
        cmd = _capture_docker_run_cmd(
            orch,
            cap_sock=cap_path,
            cap_ok=True,
        )
        volume_args = []
        for i, c in enumerate(cmd):
            if c == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])
        cap_mounts = [v for v in volume_args if "capability.sock" in v]
        assert len(cap_mounts) == 1
        assert cap_mounts[0] == f"{cap_path}:/run/rumi/capability.sock:rw"

        # 環境変数も設定されている
        env_args = []
        for i, c in enumerate(cmd):
            if c == "-e" and i + 1 < len(cmd):
                env_args.append(cmd[i + 1])
        cap_env = [e for e in env_args if e.startswith("RUMI_CAPABILITY_SOCKET=")]
        assert len(cap_env) == 1

    def test_14_egress_proxy_unavailable_skips_mount(self):
        """#14: Egress Proxy 未起動時はソケットマウントがスキップされる"""
        orch = _make_orchestrator()
        cmd = _capture_docker_run_cmd(
            orch,
            egress_raise=True,  # egress_proxy が例外を投げる
        )
        # コマンド自体は正常に生成される（エラーにならない）
        assert cmd[0] == "docker"
        assert cmd[1] == "run"

        # egress ソケットはマウントされていない
        volume_args = []
        for i, c in enumerate(cmd):
            if c == "-v" and i + 1 < len(cmd):
                volume_args.append(cmd[i + 1])
        egress_mounts = [v for v in volume_args if "egress.sock" in v]
        assert len(egress_mounts) == 0
