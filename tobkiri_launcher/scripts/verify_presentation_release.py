#!/usr/bin/env python3
"""Headlessly verify a packaged Launcher presentation catalog and IPC surface."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

CATALOG_SCHEMA = "io.tobkiri.launcher.presentation-catalog.v1"
SHELL_CONTRACT = "app.shell.v1"
PRESENTATION_COMMANDS = (
    "get_presentation_catalog",
    "select_presentation",
    "launch_selected_presentation",
)
PRESENTATION_PERMISSIONS = (
    "allow-get-presentation-catalog",
    "allow-select-presentation",
    "allow-launch-selected-presentation",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the package harness arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app",
        type=Path,
        required=True,
        help="Path to the packaged Tobkiri Launcher.app.",
    )
    parser.add_argument(
        "--launch-seconds",
        type=float,
        default=4.0,
        help="How long to keep the packaged binary running (default: 4 seconds).",
    )
    return parser.parse_args(argv)


def resource_root(app: Path) -> Path:
    """Return the runtime resource root inside a packaged app."""
    resolved = app.expanduser().resolve()
    if resolved.name == "app" and resolved.parent.name == "Resources":
        return resolved
    if resolved.suffix != ".app":
        raise RuntimeError(f"expected a .app bundle or Resources/app path: {app}")
    return resolved / "Contents" / "Resources" / "app"


def load_catalog(path: Path) -> dict[str, Any]:
    """Load and validate the package's manifest-derived catalog JSON."""
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"failed to read packaged presentation catalog {path}: {error}"
        ) from error
    if not isinstance(catalog, dict):
        raise RuntimeError(f"packaged presentation catalog is not an object: {path}")
    if catalog.get("schema") != CATALOG_SCHEMA:
        raise RuntimeError(f"unexpected packaged presentation catalog schema: {path}")
    return catalog


def verify_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Verify Base Pack/Shell compatibility, fail-closed artifacts, and identity."""
    base_packs = catalog.get("base_packs")
    shells = catalog.get("shell_providers")
    if not isinstance(base_packs, list) or len(base_packs) != 1:
        raise RuntimeError("packaged catalog must contain exactly one Base Pack")
    if not isinstance(shells, list) or not shells:
        raise RuntimeError("packaged catalog must contain Shell Providers")

    base = base_packs[0]
    if not isinstance(base, dict):
        raise RuntimeError("packaged Base Pack descriptor is invalid")
    required_capabilities = set(base.get("required_capabilities", []))
    allowed_families = set(base.get("allowed_families", []))
    identity = (
        catalog.get("default_profile_id"),
        catalog.get("default_profile_digest"),
        base.get("backend_identity_digest"),
        tuple(base.get("backend_provider_ids", [])),
        tuple(base.get("state_owners", [])),
    )
    compatible_shells: list[str] = []
    blocked_artifacts: list[str] = []
    for shell in shells:
        if not isinstance(shell, dict):
            raise RuntimeError("packaged Shell Provider descriptor is invalid")
        capabilities = set(shell.get("capabilities", []))
        approval = shell.get("approval")
        compatible = (
            shell.get("contract_id") == SHELL_CONTRACT
            and required_capabilities.issubset(capabilities)
            and shell.get("presentation_family") in allowed_families
            and isinstance(approval, dict)
            and approval.get("state") == "verified"
        )
        if compatible:
            compatible_shells.append(str(shell["provider_id"]))
        for variant in shell.get("artifact_variants", []):
            if not isinstance(variant, dict):
                raise RuntimeError("packaged artifact variant is invalid")
            if variant.get("path") is not None or variant.get("sha256") is not None:
                raise RuntimeError(
                    "uninstalled packaged artifacts must not contain install paths "
                    "or digests"
                )
            blocked_artifacts.append(str(variant["artifact_id"]))

    default_selection = catalog.get("default_selection")
    if not isinstance(default_selection, dict):
        raise RuntimeError("packaged catalog has no default selection")
    if default_selection.get("base_pack_id") != base.get("pack_id"):
        raise RuntimeError("packaged default selection does not select the Base Pack")
    if default_selection.get("shell_provider_id") not in compatible_shells:
        raise RuntimeError(
            "packaged default selection is not compatible with the Base Pack"
        )

    return {
        "base_pack_id": base.get("pack_id"),
        "compatible_shell_provider_ids": compatible_shells,
        "blocked_uninstalled_artifact_count": len(blocked_artifacts),
        "profile_identity": identity,
    }


def verify_binary(binary: Path) -> dict[str, Any]:
    """Verify the release binary contains the presentation commands and ACL entries."""
    try:
        contents = binary.read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"failed to read packaged Launcher binary {binary}: {error}"
        ) from error
    missing = [
        marker
        for marker in (*PRESENTATION_COMMANDS, *PRESENTATION_PERMISSIONS)
        if marker.encode() not in contents
    ]
    if missing:
        raise RuntimeError(
            f"packaged binary is missing presentation IPC markers: {missing}"
        )
    return {
        "binary": str(binary),
        "ipc_commands": list(PRESENTATION_COMMANDS),
        "ipc_permissions": list(PRESENTATION_PERMISSIONS),
    }


def process_ids_with_marker(marker: str) -> list[int]:
    """Find processes that inherited the harness-only environment marker."""
    result = subprocess.run(
        ["ps", "eww", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    process_ids: list[int] = []
    for line in result.stdout.splitlines():
        if marker not in line:
            continue
        try:
            process_ids.append(int(line.strip().split(maxsplit=1)[0]))
        except (IndexError, ValueError):
            continue
    return process_ids


def stop_marker_processes(marker: str) -> list[int]:
    """Stop any package children that detached from the launcher's process group."""
    stopped: list[int] = []
    for _ in range(3):
        process_ids = process_ids_with_marker(marker)
        if not process_ids:
            return stopped
        for process_id in process_ids:
            try:
                os.kill(process_id, signal.SIGTERM)
                stopped.append(process_id)
            except ProcessLookupError:
                continue
        time.sleep(0.2)
    remaining = process_ids_with_marker(marker)
    for process_id in remaining:
        try:
            os.kill(process_id, signal.SIGKILL)
            stopped.append(process_id)
        except ProcessLookupError:
            continue
    return stopped


def launch_from_relocated_cwd(binary: Path, seconds: float) -> dict[str, Any]:
    """Start the packaged binary outside the checkout and clean up its process group."""
    if seconds <= 0:
        raise RuntimeError("--launch-seconds must be greater than zero")
    marker_name = "TOBKIRI_RELEASE_HARNESS_ID"
    marker = f"{marker_name}={os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="tobkiri-release-cwd-") as cwd:
        process = subprocess.Popen(
            [os.fspath(binary)],
            cwd=cwd,
            env={**os.environ, "RUST_LOG": "debug", marker_name: str(os.getpid())},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            deadline = time.monotonic() + seconds
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate(timeout=5)
        detached_children = stop_marker_processes(marker)
        if process.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL):
            raise RuntimeError(
                f"packaged Launcher exited unexpectedly with {process.returncode}:\n"
                f"{output[-4000:]}"
            )
        lines = [line for line in output.splitlines() if line.strip()]
        return {
            "started_from_relocated_cwd": True,
            "return_code_after_cleanup": process.returncode,
            "detached_children_stopped": detached_children,
            "log_tail": lines[-8:],
        }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the resource, IPC, and relocated-cwd package checks."""
    args = parse_args(argv)
    app = args.app.expanduser().resolve()
    root = resource_root(app)
    catalog_path = root / "bundled" / "presentation_catalog.json"
    binary = app / "Contents" / "MacOS" / "tobkiri-launcher"
    report = {
        "catalog": verify_catalog(load_catalog(catalog_path)),
        "ipc": verify_binary(binary),
        "launch": launch_from_relocated_cwd(binary, args.launch_seconds),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
