from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.function_runtime import template_specs  # noqa: E402
from domain.templates.catalog_runtime import (  # noqa: E402
    current_template_catalog_generation,
    get_template_catalog_snapshot,
    invalidate_template_catalog,
)
from domain.templates.tool_policy_resolution import resolve_template_tool_policy  # noqa: E402


def _write_template(root: Path, name: str, payload: dict) -> Path:
    path = root / "templates" / name / "template.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _tool_policy_template(*, allowed_tools: list[str]) -> dict:
    return {
        "schema_version": 1,
        "id": "runtime.policy",
        "kind": "frontend",
        "version": "1.0.0",
        "status": "active",
        "pieces": [
            {
                "id": "policy",
                "kind": "tool_policy",
                "policy": {
                    "id": "runtime_tools",
                    "allowed_tools": allowed_tools,
                },
            }
        ],
    }


def _route_template(*, status: str = "active") -> dict:
    return {
        "schema_version": 1,
        "id": "runtime.route",
        "kind": "backend",
        "version": "1.0.0",
        "status": status,
        "pieces": [
            {
                "id": "route_action",
                "kind": "function",
                "role": "action",
                "action_id": "runtime_route_action",
                "block_module": "blocks.context.token_estimate",
                "method": "POST",
                "route_path": "/api/runtime-route",
            }
        ],
    }


def test_catalog_generation_changes_for_template_content(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))
    before = get_template_catalog_snapshot(defaultspack_root=tmp_path)

    _write_template(
        tmp_path,
        "policy",
        _tool_policy_template(allowed_tools=["coding_terminal_exec"]),
    )
    after = get_template_catalog_snapshot(defaultspack_root=tmp_path)

    assert before.generation != after.generation
    assert after.catalog["catalog_generation"] == after.generation
    assert after.catalog["schema_version"] == 1


def test_unrelated_file_does_not_change_catalog_generation(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))
    before = current_template_catalog_generation(defaultspack_root=tmp_path)

    note = tmp_path / "templates" / "policy" / "README.md"
    note.write_text("not part of the template catalog", encoding="utf-8")

    assert current_template_catalog_generation(defaultspack_root=tmp_path) == before


def test_provider_returns_same_snapshot_for_same_generation_and_force_reload(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))

    first = get_template_catalog_snapshot(defaultspack_root=tmp_path)
    cached = get_template_catalog_snapshot(defaultspack_root=tmp_path)
    forced = get_template_catalog_snapshot(defaultspack_root=tmp_path, force_reload=True)

    assert cached is first
    assert forced is not first
    assert forced.generation == first.generation


def test_status_change_removes_runtime_route_without_stale_cache(tmp_path):
    _write_template(tmp_path, "route", _route_template(status="active"))
    active = template_specs.template_route_items(defaultspack_root=tmp_path)
    assert [item["path"] for item in active] == ["/api/runtime-route"]

    _write_template(tmp_path, "route", _route_template(status="disabled"))
    disabled = template_specs.template_route_items(defaultspack_root=tmp_path)

    assert disabled == []


def test_policy_change_is_reflected_by_backend_resolver(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))

    first = resolve_template_tool_policy(
        {"template_tool_policy_id": "runtime_tools"},
        defaultspack_root=tmp_path,
    )
    assert first.policy["tool_allowlist"] == ["web_search"]

    _write_template(
        tmp_path,
        "policy",
        _tool_policy_template(allowed_tools=["coding_terminal_exec"]),
    )
    second = resolve_template_tool_policy(
        {"template_tool_policy_id": "runtime_tools"},
        defaultspack_root=tmp_path,
    )

    assert second.policy["tool_allowlist"] == ["coding_terminal_exec"]


def test_deleted_template_route_is_not_kept_from_previous_snapshot(tmp_path):
    path = _write_template(tmp_path, "route", _route_template(status="active"))
    assert template_specs.template_route_items(defaultspack_root=tmp_path)

    path.unlink()

    assert template_specs.template_route_items(defaultspack_root=tmp_path) == []


def test_malformed_edit_drops_previous_runtime_contribution(tmp_path):
    path = _write_template(tmp_path, "command", _route_template(status="active"))
    assert template_specs.template_route_items(defaultspack_root=tmp_path)

    path.write_text("{not json", encoding="utf-8")
    snapshot = get_template_catalog_snapshot(defaultspack_root=tmp_path)

    assert template_specs.template_route_items(defaultspack_root=tmp_path) == []
    assert any(
        diagnostic.get("code") == "template.discovery.json_parse_error"
        for diagnostic in snapshot.catalog["template_diagnostics"]
    )


def test_concurrent_snapshot_reads_share_generation(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))

    with ThreadPoolExecutor(max_workers=8) as executor:
        snapshots = list(
            executor.map(
                lambda _: get_template_catalog_snapshot(defaultspack_root=tmp_path),
                range(16),
            )
        )

    generations = {snapshot.generation for snapshot in snapshots}
    assert len(generations) == 1


def test_invalidate_discards_cached_snapshot_for_root(tmp_path):
    _write_template(tmp_path, "policy", _tool_policy_template(allowed_tools=["web_search"]))
    first = get_template_catalog_snapshot(defaultspack_root=tmp_path)

    invalidate_template_catalog(defaultspack_root=tmp_path)
    second = get_template_catalog_snapshot(defaultspack_root=tmp_path)

    assert second.generation == first.generation
    assert second is not first
