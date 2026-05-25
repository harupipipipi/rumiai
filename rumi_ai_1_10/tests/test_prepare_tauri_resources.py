from __future__ import annotations

import hashlib
import importlib.util
import io
from types import SimpleNamespace
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"


def _load_prepare_tauri_resources():
    spec = importlib.util.spec_from_file_location("prepare_tauri_resources", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_windows_uv_archive(path: Path, *, target: str, payload: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"uv-{target}/uv.exe", payload)


def _write_linux_uv_archive(path: Path, *, target: str, payload: bytes) -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name=f"uv-{target}/uv")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_stage_uv_extracts_only_after_pinned_checksum_verification(tmp_path, monkeypatch):
    module = _load_prepare_tauri_resources()
    target = "x86_64-pc-windows-msvc"
    version = "0.11.14"
    payload = b"verified uv binary"
    archive_path = tmp_path / "uv.zip"
    _write_windows_uv_archive(archive_path, target=target, payload=payload)
    checksum = _sha256(archive_path.read_bytes())

    monkeypatch.setattr(module, "UV_PINNED_VERSION", version)
    monkeypatch.setattr(module, "UV_SHA256_BY_TARGET", {target: checksum})
    monkeypatch.setattr(module, "download_to_temp", lambda url, attempts=3: archive_path)
    monkeypatch.setattr(
        module,
        "download_text",
        lambda url, attempts=3: f"{checksum} *uv-{target}.zip\n",
    )

    staged = module.stage_uv(tmp_path / "app", target, version)

    assert staged.read_bytes() == payload
    assert staged.name == "uv.exe"


def test_stage_uv_fails_on_checksum_mismatch_before_extract(tmp_path, monkeypatch):
    module = _load_prepare_tauri_resources()
    target = "x86_64-unknown-linux-gnu"
    version = "0.11.14"
    payload = b"tampered uv binary"
    archive_path = tmp_path / "uv.tar.gz"
    _write_linux_uv_archive(archive_path, target=target, payload=payload)
    actual_checksum = _sha256(archive_path.read_bytes())
    wrong_checksum = "0" * 64

    monkeypatch.setattr(module, "UV_PINNED_VERSION", version)
    monkeypatch.setattr(module, "UV_SHA256_BY_TARGET", {target: wrong_checksum})
    monkeypatch.setattr(module, "download_to_temp", lambda url, attempts=3: archive_path)
    monkeypatch.setattr(
        module,
        "download_text",
        lambda url, attempts=3: f"{actual_checksum}  uv-{target}.tar.gz\n",
    )

    with pytest.raises(RuntimeError, match="Pinned uv SHA256 does not match upstream checksum manifest"):
        module.stage_uv(tmp_path / "app", target, version)

    assert not (tmp_path / "app" / "bundled" / "uv").exists()


def test_stage_edge_haze_helper_compiles_for_apple_target(tmp_path, monkeypatch):
    module = _load_prepare_tauri_resources()
    source_root = tmp_path / "rumi_ai_1_10"
    source = source_root / module.EDGE_HAZE_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text("print(\"haze\")\n", encoding="utf-8")
    dest_root = tmp_path / "gen" / "app"

    def fake_run(args, **kwargs):
        dest = Path(args[-1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("binary", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/swiftc" if name == "swiftc" else None)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    staged = module.stage_edge_haze_helper(
        source_root,
        dest_root,
        target="aarch64-apple-darwin",
        required=True,
    )

    assert staged == dest_root / module.EDGE_HAZE_BUNDLED_REL
    assert staged.exists()
    assert staged.stat().st_mode & 0o111


def test_validate_bundle_requires_edge_haze_helper_for_release_apple_target(tmp_path):
    module = _load_prepare_tauri_resources()
    dest_root = tmp_path / "gen" / "app"
    required = [
        Path("app.py"),
        Path("requirements.txt"),
        Path("core_runtime/core_pack/core_control_panel/web/index.html"),
        Path("pack_seeds/defaultspack/ecosystem.json"),
        Path("pack_seeds/rumi_default_tools_pack/ecosystem.json"),
        Path("ecosystem/defaultspack/ecosystem.json"),
        Path("ecosystem/defaultspack/ui/shell.html"),
        Path("ecosystem/defaultspack/ui/shell-app.js"),
        Path("bundled/uv"),
        Path("bundled/pack-shell"),
    ]
    for rel in required:
        path = dest_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="edge_haze"):
        module.validate_bundle(dest_root, require_runtime_tools=True, target="aarch64-apple-darwin")
