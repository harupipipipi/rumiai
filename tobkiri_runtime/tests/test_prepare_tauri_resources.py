from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
DEFAULTSPACK_ROOT = ROOT / "tobkiri_runtime" / "ecosystem" / "defaultspack"


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


def _minimal_v4_stage(tmp_path: Path) -> Path:
    """Build a small staged resource tree from the canonical v4 inputs."""
    module = _load_prepare_tauri_resources()
    stage = tmp_path / "app"
    (stage / "core_runtime/core_pack/core_control_panel/web").mkdir(parents=True)
    (stage / "core_runtime/core_pack/core_control_panel/web/index.html").write_text(
        "<!doctype html>\n",
        encoding="utf-8",
    )
    shutil.copytree(
        ROOT / "tobkiri_runtime/core_runtime",
        stage / "core_runtime",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "ecosystem.json",
            "rumi.pack.v3.json",
        ),
    )
    for relative in module.REQUIRED_RUNTIME_BOOTSTRAP_FILES:
        source = ROOT / "tobkiri_runtime" / relative
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (stage / "requirements.txt").write_text("", encoding="utf-8")
    ui_root = stage / "ecosystem/defaultspack/ui"
    ui_root.mkdir(parents=True)
    (ui_root / "shell.html").write_text("<main></main>\n", encoding="utf-8")
    (ui_root / "shell-app.js").write_text("console.log('ok');\n", encoding="utf-8")

    pack_root = stage / "ecosystem/defaultspack"
    pack_root.mkdir(parents=True, exist_ok=True)
    for filename in (
        "pack.v4.json",
        "contracts.v4.json",
        "artifact-index.v4.json",
        "executables.v4.json",
    ):
        shutil.copy2(DEFAULTSPACK_ROOT / filename, pack_root / filename)
    shutil.copytree(
        DEFAULTSPACK_ROOT / "runtime",
        pack_root / "runtime",
        ignore=shutil.ignore_patterns(*module.EXCLUDED_DIR_NAMES, "*.pyc"),
    )
    shutil.copytree(DEFAULTSPACK_ROOT / "v4", pack_root / "v4")
    return stage


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
    wrong_checksum = "0" * 64

    monkeypatch.setattr(module, "UV_PINNED_VERSION", version)
    monkeypatch.setattr(module, "UV_SHA256_BY_TARGET", {target: wrong_checksum})
    monkeypatch.setattr(module, "download_to_temp", lambda url, attempts=3: archive_path)

    with pytest.raises(RuntimeError, match="uv archive SHA256 mismatch"):
        module.stage_uv(tmp_path / "app", target, version)

    assert not (tmp_path / "app" / "bundled" / "uv").exists()


def test_validate_bundle_accepts_canonical_v4_stage_without_legacy_authority(tmp_path):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)

    module.validate_bundle(stage, False, None, repository_root=ROOT)

    assert not list(stage.rglob("ecosystem.json"))
    assert not list(stage.rglob("rumi.pack.v3.json"))


def test_staged_bootstrap_import_and_resource_manifest_are_self_contained(tmp_path):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)

    module.validate_bundle(stage, False, None, repository_root=ROOT)
    manifest_path = module.write_runtime_resource_manifest(stage)
    module.verify_runtime_resource_manifest(stage)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest["entries"]}
    assert "core_runtime/__init__.py" in paths
    assert "core_runtime/bootstrap/runtime.py" in paths
    assert not any(path.endswith((".pyc", ".pyo")) for path in paths)
    assert not list(stage.rglob("__pycache__"))


@pytest.mark.parametrize(
    ("relative", "is_directory"),
    (("core_runtime/__pycache__", True), ("core_runtime/bootstrap.pyc", False)),
)
def test_staging_and_manifest_reject_python_bytecode(
    tmp_path, relative, is_directory
):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)
    target = stage / relative
    if is_directory:
        target.mkdir(parents=True)
    else:
        target.write_bytes(b"bytecode")

    with pytest.raises(RuntimeError, match="generated Python bytecode"):
        module.validate_bundle(stage, False, None, repository_root=ROOT)
    with pytest.raises(RuntimeError, match="generated Python bytecode"):
        module.write_runtime_resource_manifest(stage)


@pytest.mark.parametrize("case", ("missing", "tampered", "symlink"))
def test_runtime_resource_manifest_rejects_unsafe_or_changed_tree(tmp_path, case):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)
    module.write_runtime_resource_manifest(stage)
    target = stage / "core_runtime/bootstrap/runtime.py"

    if case == "missing":
        target.unlink()
    elif case == "tampered":
        target.write_bytes(target.read_bytes() + b"\n# tampered\n")
    else:
        target.unlink()
        target.symlink_to(ROOT / "tobkiri_runtime/core_runtime/bootstrap/runtime.py")

    with pytest.raises((FileNotFoundError, RuntimeError)):
        module.verify_runtime_resource_manifest(stage)


def test_validate_bundle_rejects_legacy_authority_document(tmp_path):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)
    legacy = stage / "ecosystem/defaultspack/ecosystem.json"
    legacy.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="legacy authority"):
        module.validate_bundle(stage, False, None, repository_root=ROOT)


@pytest.mark.parametrize("case", ("missing", "symlink", "tamper", "path", "unlisted"))
def test_validate_bundle_v4_preflight_rejects_drift_and_unsafe_resources(tmp_path, case):
    module = _load_prepare_tauri_resources()
    stage = _minimal_v4_stage(tmp_path)
    pack_root = stage / "ecosystem/defaultspack"

    if case == "missing":
        (pack_root / "pack.v4.json").unlink()
    elif case == "symlink":
        target = pack_root / "v4/packs/defaultspack.pack.v4.json"
        target.unlink()
        target.symlink_to(DEFAULTSPACK_ROOT / "v4/packs/defaultspack.pack.v4.json")
    elif case == "tamper":
        runtime = pack_root / "runtime/conversation.py"
        runtime.write_bytes(runtime.read_bytes() + b"\n# tampered\n")
    elif case == "path":
        lock_path = pack_root / "v4/bundle.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["entries"][0]["path"] = "../escape.json"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
    else:
        (pack_root / "v4/unlisted.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises((FileNotFoundError, RuntimeError)):
        module.validate_bundle(stage, False, None, repository_root=ROOT)
