from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "rumi_viewer" / "scripts" / "prepare_viewer_runtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_viewer_runtime", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_target_prefers_explicit_then_tauri_environment(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "host_target", lambda: "host-target")

    assert module.resolve_target("explicit-target", {module.TAURI_TARGET_ENV: "env-target"}) == "explicit-target"
    assert module.resolve_target(None, {module.TAURI_TARGET_ENV: "env-target"}) == "env-target"
    assert module.resolve_target(None, {}) == "host-target"


def test_prepare_dev_copies_repo_venv_uv_into_trusted_bundle(tmp_path, monkeypatch):
    module = _load_module()
    target = "x86_64-unknown-linux-gnu"
    source = tmp_path / ".venv" / "bin" / "uv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"uv")

    monkeypatch.setattr(module, "verify_uv_binary", lambda path: "uv 0.11.14")

    destination = module.prepare_dev(tmp_path, target)

    assert destination == tmp_path / "rumi_ai_1_10" / "bundled" / "uv"
    assert destination.read_bytes() == b"uv"
    assert os.access(destination, os.X_OK)


def test_resolve_dev_uv_source_prefers_explicit_path_over_repo_venv(tmp_path):
    module = _load_module()
    target = "x86_64-pc-windows-msvc"
    explicit = tmp_path / "managed" / "uv.exe"
    repo_uv = tmp_path / ".venv" / "Scripts" / "uv.exe"
    explicit.parent.mkdir(parents=True)
    repo_uv.parent.mkdir(parents=True)
    explicit.write_bytes(b"explicit")
    repo_uv.write_bytes(b"repo")

    resolved = module.resolve_dev_uv_source(
        tmp_path,
        target,
        {module.UV_PATH_ENV: str(explicit)},
    )

    assert resolved == explicit.resolve()


def test_prepare_dev_fails_with_actionable_repo_path_when_uv_is_missing(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match=r"\.venv/bin/uv"):
        module.prepare_dev(tmp_path, "x86_64-unknown-linux-gnu")


def test_prepare_release_builds_pack_shell_then_runs_verified_resource_preparer(tmp_path, monkeypatch):
    module = _load_module()
    manifest = tmp_path / "pack-shell" / "Cargo.toml"
    preparer_path = tmp_path / ".github" / "scripts" / "prepare_tauri_resources.py"
    manifest.parent.mkdir(parents=True)
    preparer_path.parent.mkdir(parents=True)
    manifest.write_text("[package]\nname='pack-shell'\n", encoding="utf-8")
    preparer_path.write_text("# test\n", encoding="utf-8")

    fake_preparer = SimpleNamespace(
        UV_PINNED_VERSION="0.11.14",
        UV_SHA256_BY_TARGET={"x86_64-pc-windows-msvc": "sha"},
    )
    monkeypatch.setattr(module, "load_resource_preparer", lambda _root: fake_preparer)

    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(command, *, cwd=None, capture_output=False):
        calls.append(([os.fspath(part) for part in command], cwd))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run)

    module.prepare_release(tmp_path, "x86_64-pc-windows-msvc")

    assert calls[0][0][:4] == ["cargo", "build", "--locked", "--release"]
    assert calls[0][0][4:6] == ["--target", "x86_64-pc-windows-msvc"]
    assert calls[1][0][0] == os.fspath(module.sys.executable)
    assert "--uv-version" in calls[1][0]
    assert "0.11.14" in calls[1][0]
    assert "--require-runtime-tools" in calls[1][0]


def test_prepare_release_rejects_target_without_pinned_checksum(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "load_resource_preparer",
        lambda _root: SimpleNamespace(UV_PINNED_VERSION="0.11.14", UV_SHA256_BY_TARGET={}),
    )

    with pytest.raises(RuntimeError, match="No pinned uv checksum"):
        module.prepare_release(tmp_path, "aarch64-pc-windows-msvc")
