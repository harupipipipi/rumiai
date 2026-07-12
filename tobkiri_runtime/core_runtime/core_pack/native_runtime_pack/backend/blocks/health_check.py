"""
health_check.py - バイナリ実行環境検証

バイナリ・コマンド実行に必要な環境条件を検証する。
各項目の pass/fail を JSON で返す。

検証項目:
- subprocess モジュールの利用可能性
- Docker の利用可能性（optional）
- 実行権限の付与可能性（chmod +x 相当）
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)


def run(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """バイナリ実行環境の健全性を検証する。

    subprocess の利用可能性、Docker の利用可能性、実行権限の付与可能性を
    チェックし、各項目の pass/fail を返す。

    Args:
        input_data: 実行パラメータ（現在は未使用）。
        context: 実行コンテキスト（principal_id 等）。

    Returns:
        検証結果の辞書。各項目の pass/fail と全体の status を含む。
    """
    checks: Dict[str, Dict[str, Any]] = {}

    # --- subprocess 利用可能性 ---
    checks["subprocess_available"] = _check_subprocess()

    # --- Docker 利用可能性（optional） ---
    checks["docker_available"] = _check_docker()

    # --- 実行権限の付与可能性 ---
    checks["executable_permission"] = _check_executable_permission()

    # --- 全体判定 ---
    required_checks = ["subprocess_available", "executable_permission"]
    all_required_pass = all(
        checks[name]["pass"] for name in required_checks
    )

    return {
        "success": True,
        "output": {
            "status": "healthy" if all_required_pass else "degraded",
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": sum(1 for c in checks.values() if c["pass"]),
                "failed": sum(1 for c in checks.values() if not c["pass"]),
            },
        },
    }


def _check_subprocess() -> Dict[str, Any]:
    """subprocess モジュールの利用可能性を検証する。

    Returns:
        検証結果の辞書。
    """
    try:
        proc = subprocess.run(
            ["echo", "health_check"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0 and "health_check" in (proc.stdout or ""):
            return {"pass": True, "detail": "subprocess is functional"}
        return {
            "pass": False,
            "detail": f"subprocess returned unexpected result: "
                      f"rc={proc.returncode}, stdout={proc.stdout!r}",
        }
    except Exception as exc:
        return {"pass": False, "detail": f"subprocess check failed: {exc}"}


def _check_docker() -> Dict[str, Any]:
    """Docker の利用可能性を検証する（optional）。

    Returns:
        検証結果の辞書。
    """
    if shutil.which("docker") is None:
        return {
            "pass": False,
            "detail": "docker command not found in PATH",
            "optional": True,
        }
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"pass": True, "detail": "Docker is available", "optional": True}
        return {
            "pass": False,
            "detail": f"docker info failed: rc={proc.returncode}",
            "optional": True,
        }
    except Exception as exc:
        return {
            "pass": False,
            "detail": f"Docker check failed: {exc}",
            "optional": True,
        }


def _check_executable_permission() -> Dict[str, Any]:
    """実行権限の付与が可能か検証する。

    一時ファイルを作成し、chmod +x 相当の権限を付与できるか確認する。

    Returns:
        検証結果の辞書。
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False
        ) as tmp:
            tmp.write("#!/bin/sh\necho ok\n")
            tmp_path = tmp.name

        current_mode = os.stat(tmp_path).st_mode
        os.chmod(tmp_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        if os.access(tmp_path, os.X_OK):
            return {"pass": True, "detail": "Executable permission can be granted"}
        return {"pass": False, "detail": "chmod succeeded but X_OK check failed"}
    except Exception as exc:
        return {"pass": False, "detail": f"Permission check failed: {exc}"}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
