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
        ROOT.parent / "rumi_viewer" / "src-tauri" / "src" / "host_broker.rs"
    ).read_text(encoding="utf-8")

    assert _rust_match_string_set(host_broker_source, "host_operation_allowed") == set(canonical)
    assert _rust_match_string_set(
        host_broker_source,
        "host_operation_stream_allowed",
    ) == {
        operation_id
        for operation_id, definition in canonical.items()
        if definition.get("stream_allowed") is True
    }


def _rust_match_string_set(source: str, function_name: str) -> set[str]:
    pattern = (
        rf"fn {re.escape(function_name)}\(operation: &str\) -> bool "
        r"\{\s*matches!\(\s*operation,\s*(?P<body>.*?)\s*\)\s*\}"
    )
    match = re.search(pattern, source, flags=re.DOTALL)
    assert match, f"Could not find {function_name} matches! body"
    return set(re.findall(r'"([^"]+)"', match.group("body")))
