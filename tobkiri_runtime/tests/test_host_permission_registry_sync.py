from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_defaultspack_ui_host_permission_registry_matches_canonical_registry():
    canonical = json.loads(
        (ROOT / "core_runtime" / "host_permissions" / "default_registry.json").read_text(
            encoding="utf-8"
        )
    )
    ui_registry = json.loads(
        (
            ROOT
            / "ecosystem"
            / "defaultspack"
            / "webapp"
            / "src"
            / "hostPermissions"
            / "hostPermissionRegistry.json"
        ).read_text(encoding="utf-8")
    )

    assert ui_registry == canonical


def test_viewer_host_broker_operation_allowlists_match_canonical_registry():
    canonical = json.loads(
        (ROOT / "core_runtime" / "host_permissions" / "default_registry.json").read_text(
            encoding="utf-8"
        )
    )
    host_broker_source = (
        ROOT.parent / "tobkiri_launcher" / "src-tauri" / "src" / "host_broker.rs"
    ).read_text(encoding="utf-8")

    implemented = {
        operation_id
        for operation_id, definition in canonical.items()
        if definition.get("broker_runner_implemented") is True
    }
    assert _rust_const_string_set(host_broker_source, "IMPLEMENTED_HOST_OPERATIONS") == implemented
    assert _rust_const_string_set(
        host_broker_source,
        "IMPLEMENTED_HOST_STREAM_OPERATIONS",
    ) == set()
    assert "IMPLEMENTED_HOST_OPERATIONS.contains(&operation)" in host_broker_source
    assert "IMPLEMENTED_HOST_STREAM_OPERATIONS.contains(&operation)" in host_broker_source
    assert {
        operation_id
        for operation_id, definition in canonical.items()
        if definition.get("stream_allowed") is True
    } == set()


def _rust_match_string_set(source: str, function_name: str) -> set[str]:
    pattern = (
        rf"fn {re.escape(function_name)}\(operation: &str\) -> bool "
        r"\{\s*matches!\(\s*operation,\s*(?P<body>.*?)\s*\)\s*\}"
    )
    match = re.search(pattern, source, flags=re.DOTALL)
    if not match and re.search(rf"fn {re.escape(function_name)}\(operation: &str\) -> bool \{{\s*let _ = operation;\s*false\s*\}}", source):
        return set()
    assert match, f"Could not find {function_name} matches! body"
    return set(re.findall(r'"([^"]+)"', match.group("body")))


def _rust_const_string_set(source: str, const_name: str) -> set[str]:
    pattern = rf"const {re.escape(const_name)}: &\[&str\]\s*=\s*&\[(?P<body>.*?)\];"
    match = re.search(pattern, source, flags=re.DOTALL)
    assert match, f"Could not find {const_name} string slice"
    return set(re.findall(r'"([^"]+)"', match.group("body")))
