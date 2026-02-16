"""Tests for DockerRunBuilder (M-11 DNS leak defense, L-13 build() safety guard)."""

from __future__ import annotations

import pytest

from core_runtime.docker_run_builder import DockerRunBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_builder() -> DockerRunBuilder:
    """最小限の有効なビルダーを返す。"""
    return DockerRunBuilder(name="test-container").image("python:3.11-slim")


# ---------------------------------------------------------------------------
# M-11: DNS リーク防御
# ---------------------------------------------------------------------------

class TestDnsLeakDefense:
    """--network=none 時に --dns=127.0.0.1 が付与されることを検証する。"""

    def test_dns_option_with_network_none(self) -> None:
        """デフォルト (--network=none) で --dns=127.0.0.1 が含まれる。"""
        cmd = _default_builder().build()
        assert "--dns=127.0.0.1" in cmd
        assert "--network=none" in cmd

    def test_no_dns_option_with_custom_network(self) -> None:
        """カスタムネットワーク指定時に --dns が含まれない。"""
        cmd = _default_builder().network("bridge").build()
        dns_args = [arg for arg in cmd if arg.startswith("--dns")]
        assert dns_args == [], f"Expected no --dns args, got {dns_args}"
        assert "--network=bridge" in cmd


# ---------------------------------------------------------------------------
# L-13: build() 未呼び出し検出
# ---------------------------------------------------------------------------

class TestBuildSafetyGuard:
    """iter / str の安全ガードを検証する。"""

    def test_iter_raises_typeerror(self) -> None:
        """iter(builder) で TypeError が送出される。"""
        builder = _default_builder()
        with pytest.raises(TypeError, match=r"not iterable.*\.build\(\)"):
            iter(builder)

    def test_str_warning(self) -> None:
        """str(builder) が警告メッセージを返す。"""
        builder = _default_builder()
        result = str(builder)
        assert ".build()" in result
        assert "DockerRunBuilder" in result


# ---------------------------------------------------------------------------
# 基本動作
# ---------------------------------------------------------------------------

class TestBasicBehavior:
    """build() の基本動作を検証する。"""

    def test_build_returns_list(self) -> None:
        """build() が List[str] を返す。"""
        cmd = _default_builder().build()
        assert isinstance(cmd, list)
        assert all(isinstance(item, str) for item in cmd)
        assert cmd[0] == "docker"
        assert cmd[1] == "run"

    def test_security_baseline(self) -> None:
        """セキュリティベースライン引数が含まれる。"""
        cmd = _default_builder().build()
        assert "--cap-drop=ALL" in cmd
        assert "--read-only" in cmd
        assert "--security-opt=no-new-privileges:true" in cmd
