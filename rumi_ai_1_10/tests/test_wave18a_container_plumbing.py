"""
test_wave18a_container_plumbing.py - W18-A: Container plumbing テスト

UDS ソケットマウント（Egress + Capability）および Secret ファイル注入の
テストケース（17件）。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.docker_run_builder import DockerRunBuilder


@pytest.fixture
def builder():
    return DockerRunBuilder(name="test-container")

@pytest.fixture
def tmp_component(tmp_path):
    comp_dir = tmp_path / "component"
    comp_dir.mkdir()
    setup_py = comp_dir / "setup.py"
    setup_py.write_text("def run(ctx): return {'ok': True}\n")
    return comp_dir, setup_py

@pytest.fixture
def mock_capability_proxy(tmp_path):
    base_dir = tmp_path / "capability" / "principals"
    base_dir.mkdir(parents=True)
    proxy = mock.MagicMock()
    proxy._initialized = True
    proxy._base_dir = base_dir
    proxy.ensure_principal_socket.return_value = (True, None, None)
    return proxy, base_dir

def _create_fake_sock(base_dir: Path, pack_id: str) -> Path:
    h = hashlib.sha256(pack_id.encode()).hexdigest()[:32]
    sock = base_dir / f"{h}.sock"
    sock.touch()
    return sock

def _extract_volumes(cmd: List[str]) -> List[str]:
    volumes = []
    for i, arg in enumerate(cmd):
        if arg == "-v" and i + 1 < len(cmd):
            volumes.append(cmd[i + 1])
    return volumes

def _extract_envs(cmd: List[str]) -> Dict[str, str]:
    envs = {}
    for i, arg in enumerate(cmd):
        if arg == "-e" and i + 1 < len(cmd):
            k, _, v = cmd[i + 1].partition("=")
            envs[k] = v
    return envs


class TestDockerRunBuilderSecretFile:

    def test_secret_file_generates_correct_volume(self, builder):
        """Test 1"""
        builder.secret_file("/tmp/.secret_API_KEY_abc.txt", "/run/secrets/API_KEY")
        builder.image("python:3.11-slim")
        cmd = builder.build()
        volumes = _extract_volumes(cmd)
        assert "/tmp/.secret_API_KEY_abc.txt:/run/secrets/API_KEY:ro" in volumes

    def test_secret_file_mount_is_readonly(self, builder):
        """Test 2"""
        builder.secret_file("/host/secret.txt", "/run/secrets/MY_SECRET")
        builder.image("python:3.11-slim")
        cmd = builder.build()
        volumes = _extract_volumes(cmd)
        matching = [v for v in volumes if "/run/secrets/MY_SECRET" in v]
        assert len(matching) == 1
        assert matching[0].endswith(":ro")

    def test_secret_file_returns_self_for_chaining(self, builder):
        """Test: secret_file() returns self"""
        result = builder.secret_file("/a", "/b")
        assert result is builder


class TestExecuteInContainerUDS:

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.egress_proxy.get_uds_egress_proxy_manager")
    def test_egress_uds_mounted(self, mock_get_egress, mock_subproc, tmp_component):
        """Test 3"""
        comp_dir, setup_py = tmp_component
        sock_path = Path("/tmp/rumi/egress/packs/test.sock")
        mock_mgr = mock.MagicMock()
        mock_mgr.ensure_pack_socket.return_value = (True, "", sock_path)
        mock_get_egress.return_value = mock_mgr
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id="test-pack", component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        egress_mounts = [v for v in volumes if "egress.sock" in v]
        assert len(egress_mounts) == 1
        assert egress_mounts[0].endswith(":rw")

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.capability_proxy.get_capability_proxy")
    def test_capability_uds_mounted(self, mock_get_cap, mock_subproc, tmp_component, mock_capability_proxy):
        """Test 4"""
        comp_dir, setup_py = tmp_component
        proxy, base_dir = mock_capability_proxy
        pack_id = "test-pack"
        _create_fake_sock(base_dir, pack_id)
        mock_get_cap.return_value = proxy
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id=pack_id, component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        cap_mounts = [v for v in volumes if "capability.sock" in v]
        assert len(cap_mounts) == 1
        assert cap_mounts[0].endswith(":rw")

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.egress_proxy.get_uds_egress_proxy_manager",
                side_effect=RuntimeError("Egress proxy not initialized"))
    def test_egress_proxy_not_running_skips_with_warning(self, mock_get_egress, mock_subproc, tmp_component, caplog):
        """Test 5"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        import logging
        with caplog.at_level(logging.WARNING):
            executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        egress_mounts = [v for v in volumes if "egress.sock" in v]
        assert len(egress_mounts) == 0
        assert any("Failed to mount egress socket" in r.message for r in caplog.records)

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.capability_proxy.get_capability_proxy")
    def test_capability_proxy_uninitialized_skips(self, mock_get_cap, mock_subproc, tmp_component):
        """Test 6"""
        comp_dir, setup_py = tmp_component
        proxy = mock.MagicMock()
        proxy._initialized = False
        mock_get_cap.return_value = proxy
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id="test-pack", component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        cap_mounts = [v for v in volumes if "capability.sock" in v]
        assert len(cap_mounts) == 0

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.egress_proxy.get_uds_egress_proxy_manager")
    def test_egress_env_var_set(self, mock_get_egress, mock_subproc, tmp_component):
        """Test 7"""
        comp_dir, setup_py = tmp_component
        sock_path = Path("/tmp/rumi/egress/packs/test.sock")
        mock_mgr = mock.MagicMock()
        mock_mgr.ensure_pack_socket.return_value = (True, "", sock_path)
        mock_get_egress.return_value = mock_mgr
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id="test-pack", component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        envs = _extract_envs(call_args)
        assert envs.get("RUMI_EGRESS_SOCKET") == "/run/rumi/egress.sock"

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.capability_proxy.get_capability_proxy")
    def test_capability_env_var_set(self, mock_get_cap, mock_subproc, tmp_component, mock_capability_proxy):
        """Test 8"""
        comp_dir, setup_py = tmp_component
        proxy, base_dir = mock_capability_proxy
        pack_id = "test-pack"
        _create_fake_sock(base_dir, pack_id)
        mock_get_cap.return_value = proxy
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id=pack_id, component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        envs = _extract_envs(call_args)
        assert envs.get("RUMI_CAPABILITY_SOCKET") == "/run/rumi/capability.sock"


class TestSecretInjection:

    def test_secret_tmpfile_permissions(self):
        """Test 9"""
        fd, path = tempfile.mkstemp(prefix=".secret_test_", suffix=".txt")
        try:
            os.write(fd, b"secret-value")
            os.close(fd)
            os.chmod(path, 0o600)
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert mode == 0o600
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    @mock.patch("subprocess.run")
    def test_secret_tmpfiles_cleaned_in_finally(self, mock_subproc, tmp_component):
        """Test 10"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        mock_sgm = mock.MagicMock()
        mock_sgm.get_granted_secrets.return_value = {"TEST_KEY": "test_value"}

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True

        created_files = []
        original_mkstemp = tempfile.mkstemp
        def tracking_mkstemp(**kwargs):
            fd, path = original_mkstemp(**kwargs)
            if ".secret_" in path:
                created_files.append(path)
            return fd, path

        with mock.patch(
            "core_runtime.secure_executor.get_secrets_grant_manager",
            return_value=mock_sgm, create=True,
        ), mock.patch("tempfile.mkstemp", side_effect=tracking_mkstemp):
            executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        for f in created_files:
            assert not os.path.exists(f), f"Secret tmpfile not cleaned: {f}"

    @mock.patch("subprocess.run")
    def test_secrets_grant_manager_import_error_skips(self, mock_subproc, tmp_component):
        """Test 11"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True

        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if "secrets_grant_manager" in name:
                raise ImportError("No module named 'core_runtime.secrets_grant_manager'")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=mock_import):
            result = executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        assert result.success is True

    @mock.patch("subprocess.run")
    def test_only_granted_secrets_injected(self, mock_subproc, tmp_component):
        """Test 12"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        mock_sgm = mock.MagicMock()
        mock_sgm.get_granted_secrets.return_value = {"API_KEY": "sk-123", "TOKEN": "tok-456"}

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True

        with mock.patch(
            "core_runtime.secure_executor.get_secrets_grant_manager",
            return_value=mock_sgm, create=True,
        ):
            executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        envs = _extract_envs(call_args)
        secret_volumes = [v for v in volumes if "/run/secrets/" in v]
        assert len(secret_volumes) == 2
        assert "RUMI_SECRET_API_KEY" in envs
        assert "RUMI_SECRET_TOKEN" in envs
        assert "RUMI_SECRET_SECRET_X" not in envs

    @mock.patch("subprocess.run")
    def test_secret_container_path_format(self, mock_subproc, tmp_component):
        """Test 13"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        mock_sgm = mock.MagicMock()
        mock_sgm.get_granted_secrets.return_value = {"MY_API_KEY": "value123"}

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True

        with mock.patch(
            "core_runtime.secure_executor.get_secrets_grant_manager",
            return_value=mock_sgm, create=True,
        ):
            executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        secret_vols = [v for v in volumes if "/run/secrets/" in v]
        assert len(secret_vols) == 1
        assert ":/run/secrets/MY_API_KEY:ro" in secret_vols[0]

    @mock.patch("subprocess.run")
    def test_secret_env_points_to_file_path(self, mock_subproc, tmp_component):
        """Test 14"""
        comp_dir, setup_py = tmp_component
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        mock_sgm = mock.MagicMock()
        mock_sgm.get_granted_secrets.return_value = {"DB_PASS": "pw123"}

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True

        with mock.patch(
            "core_runtime.secure_executor.get_secrets_grant_manager",
            return_value=mock_sgm, create=True,
        ):
            executor._execute_in_container(
                pack_id="test-pack", component_id="comp1", phase="setup",
                file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
            )
        call_args = mock_subproc.call_args[0][0]
        envs = _extract_envs(call_args)
        assert envs["RUMI_SECRET_DB_PASS"] == "/run/secrets/DB_PASS"


class TestExecuteLibUDS:

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.egress_proxy.get_uds_egress_proxy_manager")
    def test_lib_egress_uds_mounted(self, mock_get_egress, mock_subproc, tmp_component):
        """Test 15"""
        comp_dir, setup_py = tmp_component
        lib_file = comp_dir / "install.py"
        lib_file.write_text("def run(ctx): return {'ok': True}\n")
        sock_path = Path("/tmp/rumi/egress/packs/test.sock")
        mock_mgr = mock.MagicMock()
        mock_mgr.ensure_pack_socket.return_value = (True, "", sock_path)
        mock_get_egress.return_value = mock_mgr
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        pack_data_dir = comp_dir / "data"
        pack_data_dir.mkdir()
        executor._execute_lib_in_container(
            pack_id="test-pack", lib_type="install", lib_file=lib_file,
            pack_data_dir=pack_data_dir, context={}, timeout=60,
            start_time=__import__("time").time(),
        )
        call_args = mock_subproc.call_args[0][0]
        volumes = _extract_volumes(call_args)
        egress_mounts = [v for v in volumes if "egress.sock" in v]
        assert len(egress_mounts) == 1
        assert egress_mounts[0].endswith(":rw")
        envs = _extract_envs(call_args)
        assert envs.get("RUMI_EGRESS_SOCKET") == "/run/rumi/egress.sock"


class TestPermissiveMode:

    def test_host_execution_no_uds_or_secrets(self, tmp_component):
        """Test 16"""
        comp_dir, setup_py = tmp_component
        setup_py.write_text("def run(ctx): return {'mode': 'host'}\n")

        from core_runtime.secure_executor import SecureExecutor
        with mock.patch.dict(os.environ, {"RUMI_SECURITY_MODE": "permissive"}):
            executor = SecureExecutor()
            executor._docker_available = False
        result = executor._execute_on_host_with_warning(
            pack_id="test-pack", component_id="comp1", phase="setup",
            file_path=setup_py, context={},
        )
        assert result.execution_mode == "host_permissive"


class TestNetworkNoneMaintained:

    @mock.patch("subprocess.run")
    @mock.patch("core_runtime.egress_proxy.get_uds_egress_proxy_manager")
    def test_network_none_after_uds_mount(self, mock_get_egress, mock_subproc, tmp_component):
        """Test 17"""
        comp_dir, setup_py = tmp_component
        sock_path = Path("/tmp/rumi/egress/packs/test.sock")
        mock_mgr = mock.MagicMock()
        mock_mgr.ensure_pack_socket.return_value = (True, "", sock_path)
        mock_get_egress.return_value = mock_mgr
        mock_subproc.return_value = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")

        from core_runtime.secure_executor import SecureExecutor
        executor = SecureExecutor()
        executor._docker_available = True
        executor._execute_in_container(
            pack_id="test-pack", component_id="comp1", phase="setup",
            file_path=setup_py, component_dir=comp_dir, context={}, timeout=30,
        )
        call_args = mock_subproc.call_args[0][0]
        assert "--network=none" in call_args
        assert "--cap-drop=ALL" in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
