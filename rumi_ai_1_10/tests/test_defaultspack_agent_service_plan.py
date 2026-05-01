from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_capability_catalog_loads_plan_manifest():
    from domain.capability.catalog import CapabilityCatalog

    catalog = CapabilityCatalog(DEFAULTSPACK_ROOT)
    manifest = catalog.manifest()

    assert manifest["local_first"] is True
    assert manifest["core_requires_api_key"] is False
    assert manifest["default_profile"] == "defaultspack.local_agent"
    assert manifest["counts"]["capabilities"] >= 11
    assert manifest["counts"]["profiles"] >= 5
    capability_ids = {item["id"] for item in manifest["capabilities"]}
    assert {"local_file", "terminal", "git", "safety", "artifact", "compact", "research"} <= capability_ids


def test_fallback_routes_expose_agent_service_and_coding_surfaces():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in _FALLBACK_HTTP_ROUTE_SPECS}

    assert ("GET", "/api/capabilities", "blocks.capability.list") in routes
    assert ("GET", "/api/agent-service/manifest", "blocks.capability.manifest") in routes
    assert ("POST", "/api/coding/files/diff", "blocks.coding.file_diff") in routes
    assert ("POST", "/api/coding/terminal/exec", "blocks.coding.terminal_exec") in routes
    assert ("POST", "/api/context/compact", "blocks.context.compact") in routes
    assert ("POST", "/api/artifacts", "blocks.artifact.create") in routes
    assert ("POST", "/api/research/local-search", "blocks.research.local_search") in routes


def test_file_ops_diff_patch_snapshot_restore(tmp_path):
    from domain.coding.file_ops import FileOps

    ops = FileOps(tmp_path)
    ops.create_file("notes/example.txt", "hello world\n")

    diff = ops.diff_text("notes/example.txt", "hello rumi\n")
    assert "hello world" in diff
    assert "hello rumi" in diff

    patch = ops.apply_patch_text("notes/example.txt", "world", "rumi")
    assert patch["patched"] is True
    assert ops.read_file("notes/example.txt") == "hello rumi\n"

    snapshot = ops.snapshot(["notes/example.txt"])
    ops.write_file("notes/example.txt", "changed\n")
    restored = ops.restore_snapshot(snapshot["snapshot_id"], ["notes/example.txt"])
    assert restored["restored"] == ["notes/example.txt"]
    assert ops.read_file("notes/example.txt") == "hello rumi\n"


def test_terminal_exec_requires_approval_for_medium_risk_and_runs_read_only(tmp_path):
    from domain.coding.terminal import Terminal

    terminal = Terminal(tmp_path)

    read_only = terminal.execute("pwd", approved=False)
    assert read_only["exit_code"] == 0
    assert read_only["risk"]["risk_level"] == "low"

    medium = terminal.execute("python3 -c 'print(42)'", approved=False)
    assert medium["approval_required"] is True
    assert medium["exit_code"] is None

    approved = terminal.execute("python3 -c 'print(42)'", approved=True)
    assert approved["exit_code"] == 0
    assert approved["stdout"].strip() == "42"


def test_git_ops_returns_real_status_and_diff(tmp_path):
    from domain.coding.git_ops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "file.txt").write_text("two\n", encoding="utf-8")

    git = GitOps(tmp_path)
    status = git.status()
    diff = git.diff()

    assert status["clean"] is False
    assert "file.txt" in status["modified"]
    assert "-one" in diff["diff"]
    assert "+two" in diff["diff"]


def test_artifact_store_is_local_and_versioned(tmp_path):
    from domain.artifact.store import ArtifactStore

    pack_root = tmp_path / "defaultspack"
    store = ArtifactStore(pack_root)
    artifact = store.create("markdown", "Plan", "# Plan\n", path="plans/plan.md", source_task="test")

    assert artifact["version"] == 1
    assert artifact["content_ref"] == "user_data/artifacts/plans/plan.md"
    assert store.list()[0]["artifact_id"] == artifact["artifact_id"]
    assert store.get(artifact["artifact_id"])["content"] == "# Plan\n"


def test_direct_block_calls_do_not_trust_client_approved_for_privileged_ops(tmp_path):
    from ecosystem.defaultspack.blocks.coding import file_write, terminal_exec, git_commit

    write_res = file_write.run({"path": "notes.txt", "content": "x", "approved": True}, context=None)
    assert write_res["status"] == "ok"
    assert write_res["data"]["approval_required"] is True

    term_res = terminal_exec.run({"command": "python3 -c 'print(42)'", "approved": True, "workspace_root": str(tmp_path)}, context=None)
    assert term_res["status"] == "ok"
    assert term_res["data"]["approval_required"] is True

    commit_res = git_commit.run({"message": "x", "approved": True, "workspace_root": str(tmp_path)}, context=None)
    assert commit_res["status"] == "ok"
    assert commit_res["data"]["approval_required"] is True
