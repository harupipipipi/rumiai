from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _init_git_repo(path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for E2E smoke tests")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)


def _git_commit_all(path: Path, message: str = "initial") -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)


def test_mimo_defaultspack_self_improvement_smoke(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import (
        create_mimo_profile,
        MIMO_PROFILE_ID,
        MIMO_ROLE_MAP,
    )
    from domain.coding.git_ops import GitOps

    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_SELF_IMPROVEMENT_STATE_PATH", str(tmp_path / "si_state.json"))

    (tmp_path / "target.py").write_text("def hello():\n    return 'old'\n", encoding="utf-8")
    (tmp_path / "test_target.py").write_text(
        "from target import hello\n\ndef test_hello():\n    assert hello() == 'old'\n",
        encoding="utf-8",
    )
    (tmp_path / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
    _git_commit_all(tmp_path)

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si_state.json")
    status = runtime.bootstrap()
    assert status["running"] is True
    assert status["profile_id"] == MIMO_PROFILE_ID

    runtime.add_task(
        "smoke_01",
        "Fix hello() return value",
        expected_outcome="hello returns 'new'",
    )
    runtime.start_task("smoke_01")

    content = (tmp_path / "target.py").read_text(encoding="utf-8")
    assert "old" in content
    runtime.record_tool_call("coding_file_read", {"path": "target.py"})

    (tmp_path / "target.py").write_text(
        content.replace("return 'old'", "return 'new'"),
        encoding="utf-8",
    )
    runtime.record_tool_call("coding_file_patch", {"path": "target.py"})

    (tmp_path / "test_target.py").write_text(
        "from target import hello\n\ndef test_hello():\n    assert hello() == 'new'\n",
        encoding="utf-8",
    )

    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "test_target.py"), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    runtime.record_test_result(
        "pytest test_target.py",
        test_result.returncode,
        test_result.stdout + test_result.stderr,
    )

    git = GitOps(tmp_path)
    commit_result = git.commit("fix: hello returns new", paths=["target.py", "test_target.py"])
    runtime.record_commit(
        commit_result["commit_hash"],
        commit_result["message"],
        paths=["target.py", "test_target.py"],
    )

    runtime.complete_task("smoke_01", {
        "files_read": ["target.py"],
        "files_modified": ["target.py", "test_target.py"],
        "test_exit_code": test_result.returncode,
        "commit_hash": commit_result["commit_hash"],
    })

    final_status = runtime.status()
    assert final_status["completed_count"] == 1
    assert final_status["last_self_improvement_result"]["commit_hash"] == commit_result["commit_hash"]

    git_status = git.status()
    assert "unrelated.txt" not in git_status.get("modified", [])

    manifest = runtime.manifest()
    assert manifest["role_map"]["main"] == MIMO_ROLE_MAP["main"]
    assert manifest["role_map"]["vision"] == MIMO_ROLE_MAP["vision"]
    assert manifest["role_map"]["fast"] == MIMO_ROLE_MAP["fast"]


def test_mimo_defaultspack_patch_test_commit_loop(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.coding.git_ops import GitOps

    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_SELF_IMPROVEMENT_STATE_PATH", str(tmp_path / "si_state.json"))

    (tmp_path / "math_utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_math_utils.py").write_text(
        "from math_utils import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (tmp_path / "keep_dirty.txt").write_text("original\n", encoding="utf-8")
    _git_commit_all(tmp_path)

    (tmp_path / "keep_dirty.txt").write_text("modified\n", encoding="utf-8")

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si_state.json")
    runtime.bootstrap()

    runtime.add_task("loop_01", "Add multiply function")
    runtime.start_task("loop_01")

    (tmp_path / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_math_utils.py").write_text(
        "from math_utils import add, multiply\n\ndef test_add():\n    assert add(1, 2) == 3\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n",
        encoding="utf-8",
    )

    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "test_math_utils.py"), "-v"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert test_result.returncode == 0, f"Tests failed: {test_result.stdout}\n{test_result.stderr}"

    git = GitOps(tmp_path)
    commit_result = git.commit("feat: add multiply function", paths=["math_utils.py", "test_math_utils.py"])
    runtime.record_commit(commit_result["commit_hash"], commit_result["message"], paths=["math_utils.py", "test_math_utils.py"])
    runtime.complete_task("loop_01", {"commit_hash": commit_result["commit_hash"]})

    status = git.status()
    assert "keep_dirty.txt" in status["modified"]
    assert "math_utils.py" not in status["modified"]
    assert "test_math_utils.py" not in status["modified"]


def test_mimo_self_improvement_records_result_metadata(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    monkeypatch.setenv("RUMI_SELF_IMPROVEMENT_STATE_PATH", str(tmp_path / "si_state.json"))
    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si_state.json")
    runtime.bootstrap()

    runtime.add_task("meta_01", "Record metadata test")
    runtime.start_task("meta_01")
    runtime.record_tool_call("coding_file_read", {"path": "test.py"})
    runtime.record_tool_call("coding_file_patch", {"path": "test.py"})
    runtime.record_test_result("pytest test.py", 0, "passed")
    runtime.record_commit("deadbeef", "fix: test", paths=["test.py"])
    runtime.complete_task("meta_01", {
        "tools_used": ["coding_file_read", "coding_file_patch"],
        "test_exit_code": 0,
        "commit_hash": "deadbeef",
    })

    state = json.loads((tmp_path / "si_state.json").read_text(encoding="utf-8"))
    assert state["last_self_improvement_result"]["commit_hash"] == "deadbeef"
    assert state["last_test_result"]["exit_code"] == 0
    assert state["last_commit"]["paths"] == ["test.py"]
    assert len(state["events"]) >= 4


def test_mimo_self_improvement_commit_uses_paths_not_all_tracked(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.coding.git_ops import GitOps

    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_SELF_IMPROVEMENT_STATE_PATH", str(tmp_path / "si_state.json"))

    (tmp_path / "patched.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "untouched.py").write_text("y = 2\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / "patched.py").write_text("x = 10\n", encoding="utf-8")
    (tmp_path / "untouched.py").write_text("y = 20\n", encoding="utf-8")

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si_state.json")
    runtime.bootstrap()
    runtime.add_task("p1", "Patch one file")
    runtime.start_task("p1")

    git = GitOps(tmp_path)
    result = git.commit("update patched.py only", paths=["patched.py"])
    runtime.record_commit(result["commit_hash"], result["message"], paths=["patched.py"])
    runtime.complete_task("p1", {"commit_hash": result["commit_hash"]})

    status = git.status()
    assert "untouched.py" in status["modified"]
    assert "patched.py" not in status["modified"]


def test_mimo_cannot_commit_env_file(tmp_path, monkeypatch):
    from domain.coding.git_ops import GitOps

    _init_git_repo(tmp_path)
    (tmp_path / ".env").write_text("TOKEN=clean\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / ".env").write_text("TOKEN=dirty\n", encoding="utf-8")

    git = GitOps(tmp_path)
    with pytest.raises(PermissionError, match="Restricted"):
        git.commit("leak env", paths=[".env"])


def test_mimo_commit_result_records_selected_paths(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.coding.git_ops import GitOps

    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_SELF_IMPROVEMENT_STATE_PATH", str(tmp_path / "si_state.json"))

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 2\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / "a.py").write_text("a = 10\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 20\n", encoding="utf-8")

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si_state.json")
    runtime.bootstrap()

    git = GitOps(tmp_path)
    result = git.commit("update a only", paths=["a.py"])
    runtime.record_commit(result["commit_hash"], result["message"], paths=["a.py"])

    status = runtime.status()
    assert status["last_commit"]["paths"] == ["a.py"]
    assert "a.py" in str(status["last_commit"])
