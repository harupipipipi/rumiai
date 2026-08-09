"""Fail-closed Host-to-PackVM artifact materialization regressions."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from ecosystem.defaultspack.backend.sandbox.isolation.resources import (
    packvm_guest_runner,
)
import tobkiri_host.artifact_materialization as materialization_module
from tobkiri_host.artifact_compiler import compile_pack_root
from tobkiri_host.artifact_materialization import capture_materialized_artifact
from tobkiri_host.contracts import OperationCatalog, OperationRoute
from tobkiri_host.errors import InvalidArtifactError
from tobkiri_host.models import OpaqueAuthorityRef


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = RUNTIME_ROOT / "tests" / "fixtures" / "conformance_minimal_echo_pack"
PACK_ID = "conformance.minimal.echo"


def _copied_binding(tmp_path: Path):
    root = tmp_path / PACK_ID
    shutil.copytree(FIXTURE, root)
    compiled = compile_pack_root(root)
    (contract_id, operation_id), metadata = next(iter(compiled.routes.items()))
    function = compiled.artifact.functions[0]
    route = OperationRoute(
        contract_id=contract_id,
        operation_id=operation_id,
        artifact_digest=compiled.artifact.digest,
        function_id=function.function_id,
        variant_id=str(metadata["variant_id"]),
        execution_domain_profile=str(metadata["execution_domain_profile"]),
        materialization_mode=str(metadata["materialization_mode"]),
        target_principal_ref=OpaqueAuthorityRef("authority:materialization-test"),
    )
    binding = OperationCatalog((compiled.artifact,), (route,)).resolve(
        contract_id,
        operation_id,
        ">=1,<2",
    )
    return root, binding


def test_capture_contains_only_digest_pinned_regular_files(tmp_path: Path) -> None:
    root, binding = _copied_binding(tmp_path)
    captured = capture_materialized_artifact(root, binding)
    assert captured.pack_id == PACK_ID
    assert captured.artifact_digest == binding.artifact.digest
    assert captured.implementation_digest == binding.function.implementation_digest
    assert all(not Path(item.path).is_absolute() for item in captured.files)
    assert {item.path for item in captured.files} >= {
        "artifact-index.v4.json",
        "contracts.v4.json",
        "executables.v4.json",
        "pack.v4.json",
        "runtime/echo.py",
    }
    request = captured.request_payload(nonce="a" * 64)
    assert "host_path" not in request
    assert "pack_root" not in request


def test_capture_rejects_symlink_and_wrong_digest(tmp_path: Path) -> None:
    root, binding = _copied_binding(tmp_path)
    runtime = root / "runtime" / "echo.py"
    outside = tmp_path / "outside.py"
    outside.write_bytes(runtime.read_bytes())
    runtime.unlink()
    runtime.symlink_to(outside)
    with pytest.raises(InvalidArtifactError, match="unavailable"):
        capture_materialized_artifact(root, binding)

    runtime.unlink()
    runtime.write_text("tampered = True\n", encoding="utf-8")
    with pytest.raises(InvalidArtifactError, match="digest"):
        capture_materialized_artifact(root, binding)


def test_capture_rejects_pack_root_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, binding = _copied_binding(tmp_path)
    replacement = tmp_path / "replacement"
    shutil.copytree(FIXTURE, replacement)
    original_reader = materialization_module._read_regular_file
    swapped = False

    def swap_after_first_read(descriptor: int, relative: str):
        nonlocal swapped
        result = original_reader(descriptor, relative)
        if not swapped:
            swapped = True
            root.rename(tmp_path / "original")
            replacement.rename(root)
        return result

    monkeypatch.setattr(
        materialization_module,
        "_read_regular_file",
        swap_after_first_read,
    )
    with pytest.raises(InvalidArtifactError, match="root changed"):
        capture_materialized_artifact(root, binding)


def test_guest_stage_is_read_only_replay_safe_and_reverified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, binding = _copied_binding(tmp_path)
    captured = capture_materialized_artifact(root, binding)
    guest_root = tmp_path / "guest-artifacts"
    monkeypatch.setattr(packvm_guest_runner, "ARTIFACT_ROOT", guest_root)
    monkeypatch.setattr(packvm_guest_runner.os, "geteuid", lambda: 0)
    request = captured.request_payload(nonce="a" * 64)
    response = packvm_guest_runner._materialize(request)
    assert response["ok"] is True
    identity = str(response["guest_artifact_identity"])
    with pytest.raises(ValueError, match="replay"):
        packvm_guest_runner._materialize(request)
    retry = packvm_guest_runner._materialize(
        captured.request_payload(nonce="b" * 64)
    )
    assert retry["guest_artifact_identity"] == identity

    invoke = {
        "artifact_digest": captured.artifact_digest,
        "materialization_digest": captured.materialization_digest,
        "guest_artifact_identity": identity,
    }
    assert packvm_guest_runner._verify_invocation_artifact(invoke) == identity
    target = (
        guest_root
        / captured.artifact_digest.removeprefix("sha256:")
        / captured.materialization_digest.removeprefix("sha256:")
    )
    runtime = target / "runtime" / "echo.py"
    target.chmod(0o700)
    runtime.parent.chmod(0o700)
    runtime.chmod(0o600)
    runtime.write_text("tampered = True\n", encoding="utf-8")
    runtime.chmod(0o400)
    runtime.parent.chmod(0o500)
    target.chmod(0o500)
    with pytest.raises(ValueError, match="digest changed"):
        packvm_guest_runner._verify_invocation_artifact(invoke)
    expected_runtime = next(
        item.content for item in captured.files if item.path == "runtime/echo.py"
    )
    target.chmod(0o700)
    runtime.parent.chmod(0o700)
    runtime.chmod(0o600)
    runtime.write_bytes(expected_runtime)
    runtime.chmod(0o400)
    extra = target / "unexpected.py"
    extra.write_text("pass\n", encoding="utf-8")
    extra.chmod(0o400)
    runtime.parent.chmod(0o500)
    target.chmod(0o500)
    with pytest.raises(ValueError, match="inventory changed"):
        packvm_guest_runner._verify_invocation_artifact(invoke)
