from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import generate_packaged_defaultspack_v4_bundle as generator


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"
SOURCE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
SOURCE_TREE = "89abcdef0123456789abcdef0123456789abcdef"


def _linux_source(path: Path, payload: bytes = b"original") -> Path:
    """Create a small recognized x86_64 ELF fixture."""
    path.write_bytes(
        b"\x7fELF\x02\x01\x01\x00"
        + b"\x00" * 10
        + b">\x00"
        + payload
    )
    path.chmod(0o755)
    return path


def _bundle_roots(root: Path) -> tuple[Path, Path]:
    """Create a clean source bundle and empty artifact output roots."""
    bundle = root / "defaultspack" / "v4"
    artifacts = root / "defaultspack" / "platform-artifacts"
    shutil.copytree(SOURCE_BUNDLE, bundle)
    return bundle, artifacts


def _bytes(root: Path) -> dict[str, bytes]:
    """Snapshot all regular bytes below one output root."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _stage(
    source: Path,
    bundle: Path,
    artifacts: Path,
    *,
    relative_path: str = "Tobkiri.AppImage",
    entrypoint: str = "Tobkiri.AppImage",
) -> None:
    generator.stage_packaged_bundle(
        source_artifact=source,
        bundle_root=bundle,
        artifact_root=artifacts,
        relative_path=relative_path,
        entrypoint=entrypoint,
        platform="linux",
        architecture="x86_64",
        bundle_identity="io.tobkiri.shell.tauri",
        source_commit=SOURCE_COMMIT,
        source_tree=SOURCE_TREE,
        source_clean=True,
        source_snapshot_root=ROOT,
    )


@pytest.mark.parametrize(
    ("relative_path", "entrypoint"),
    [
        ("../outside", "Tobkiri.AppImage"),
        ("/outside", "Tobkiri.AppImage"),
        ("Tobkiri.AppImage", "../outside"),
        ("Tobkiri.AppImage", "/outside"),
    ],
)
def test_generator_rejects_normalized_escape_before_copy(
    tmp_path: Path, relative_path: str, entrypoint: str
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    source = _linux_source(tmp_path / "source")
    outside = tmp_path / "outside"
    with pytest.raises(ValueError, match="unsafe"):
        _stage(
            source,
            bundle,
            artifacts,
            relative_path=relative_path,
            entrypoint=entrypoint,
        )
    assert not outside.exists()
    assert _bytes(artifacts) == {}
    assert json.loads((bundle / "bundle.lock.json").read_text())["entries"]


def test_generator_rejects_destination_symlink_without_writing_outside(
    tmp_path: Path,
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (artifacts.parent).mkdir(parents=True, exist_ok=True)
    artifacts.symlink_to(outside, target_is_directory=True)
    source = _linux_source(tmp_path / "source")
    with pytest.raises(ValueError, match="symlink"):
        _stage(source, bundle, artifacts)
    assert _bytes(outside) == {}


def test_generator_second_pack_write_fault_preserves_existing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    artifacts.mkdir(parents=True)
    (artifacts / "keep.txt").write_bytes(b"existing-artifact")
    source = _linux_source(tmp_path / "source")
    before_bundle = _bytes(bundle)
    before_artifacts = _bytes(artifacts)
    original_write = generator._write_json

    def fail_second_pack(path: Path, value: object) -> None:
        if path.name == "runtime.tauri.application.default.pack.v4.json":
            raise OSError("injected second Pack write fault")
        original_write(path, value)

    monkeypatch.setattr(generator, "_write_json", fail_second_pack)
    with pytest.raises(OSError, match="second Pack"):
        _stage(source, bundle, artifacts)
    assert _bytes(bundle) == before_bundle
    assert _bytes(artifacts) == before_artifacts
    assert not list(tmp_path.glob(".tobkiri-defaultspack-transaction-*"))


def test_generator_source_replace_after_snapshot_seals_original_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    source = _linux_source(tmp_path / "source", b"original")
    original_snapshot = generator._snapshot_artifact

    def replace_after_snapshot(source_path: Path, destination: Path) -> Path:
        result = original_snapshot(source_path, destination)
        _linux_source(source_path, b"replaced-after-snapshot")
        return result

    monkeypatch.setattr(generator, "_snapshot_artifact", replace_after_snapshot)
    _stage(source, bundle, artifacts)
    assert (artifacts / "Tobkiri.AppImage").read_bytes().endswith(b"original")
    assert source.read_bytes().endswith(b"replaced-after-snapshot")


def test_generator_revalidates_only_staged_artifact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    source = _linux_source(tmp_path / "source")
    original_verify = generator.verify_platform_artifact
    roots: list[Path] = []

    def observe(root: Path, variant: dict[str, object]) -> Path:
        roots.append(root)
        return original_verify(root, variant)

    monkeypatch.setattr(generator, "verify_platform_artifact", observe)
    _stage(source, bundle, artifacts)
    assert roots
    assert all(root != source.parent for root in roots)
    assert all(root.is_relative_to(tmp_path) for root in roots)


def test_generator_two_passes_have_identical_bytes(tmp_path: Path) -> None:
    source = _linux_source(tmp_path / "source")
    first_bundle, first_artifacts = _bundle_roots(tmp_path / "first")
    second_bundle, second_artifacts = _bundle_roots(tmp_path / "second")
    _stage(source, first_bundle, first_artifacts)
    _stage(source, second_bundle, second_artifacts)
    assert _bytes(first_bundle) == _bytes(second_bundle)
    assert _bytes(first_artifacts) == _bytes(second_artifacts)
    assert not list(tmp_path.rglob(".tobkiri-defaultspack-transaction-*"))


def test_generator_existing_output_rollback_on_publish_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    artifacts.mkdir(parents=True)
    (artifacts / "keep.txt").write_bytes(b"keep")
    source = _linux_source(tmp_path / "source")
    before_bundle = _bytes(bundle)
    before_artifacts = _bytes(artifacts)
    original_replace = generator.os.replace
    calls = 0

    def fail_second_replace(source_path: str, destination_path: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publish fault")
        original_replace(source_path, destination_path)

    monkeypatch.setattr(generator.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="publish fault"):
        _stage(source, bundle, artifacts)
    assert _bytes(bundle) == before_bundle
    assert _bytes(artifacts) == before_artifacts


@pytest.mark.parametrize(
    "source_commit", ["working-tree", "short", "a" * 40, "refs/heads/main"]
)
def test_generator_rejects_unverified_source_revision(
    tmp_path: Path, source_commit: str
) -> None:
    bundle, artifacts = _bundle_roots(tmp_path)
    source = _linux_source(tmp_path / "source")
    with pytest.raises(ValueError, match="full lowercase 40-hex identity"):
        generator._package_transaction(
            source_artifact=source,
            bundle_root=bundle,
            artifact_root=artifacts,
            relative_path="Tobkiri.AppImage",
            entrypoint="Tobkiri.AppImage",
            platform="linux",
            architecture="x86_64",
            bundle_identity="io.tobkiri.shell.tauri",
            source_commit=source_commit,
            source_tree=SOURCE_TREE,
            source_clean=True,
            source_snapshot_root=ROOT,
        )


def test_generator_requires_exact_clean_snapshot_provenance(tmp_path: Path) -> None:
    """Formal source identity and clean state are required before staging."""
    bundle, artifacts = _bundle_roots(tmp_path)
    source = _linux_source(tmp_path / "source")
    with pytest.raises(ValueError, match="clean attestation"):
        generator._package_transaction(
            source_artifact=source,
            bundle_root=bundle,
            artifact_root=artifacts,
            relative_path="Tobkiri.AppImage",
            entrypoint="Tobkiri.AppImage",
            platform="linux",
            architecture="x86_64",
            bundle_identity="io.tobkiri.shell.tauri",
            source_commit=SOURCE_COMMIT,
            source_tree=SOURCE_TREE,
            source_clean=False,
            source_snapshot_root=ROOT,
        )


def test_generator_has_no_git_subprocess_boundary() -> None:
    """The generator module cannot spawn or discover Git."""
    assert not hasattr(generator, "subprocess")
    assert not hasattr(generator, "_run_bound_git")
