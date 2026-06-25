from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


def test_adaptive_dispatch_compile_apply_and_activity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import AdaptiveRuntimeService, dispatch

    compiled = dispatch(
        "onboarding_compile",
        {"profile_id": "coding", "answers": {"profile_id": "coding", "preset_id": "maximum_local_autonomy"}},
        {},
    )
    assert compiled["status"] == "ok"
    plan = compiled["data"]["plan"]

    applied = dispatch("onboarding_apply", {"profile_id": "coding", "plan": plan}, {})
    assert applied["status"] == "ok"
    assert applied["data"]["applied"] is True

    frozen = dispatch("freeze_set", {"profile_id": "coding", "frozen": True, "reason": "test"}, {})
    assert frozen["status"] == "ok"
    snapshot = AdaptiveRuntimeService(profile_id="coding").activity_snapshot()
    assert snapshot["freeze"]["frozen"] is True
    assert snapshot["events"]
    blocked = dispatch("lease_acquire", {"profile_id": "coding", "resource": "src/App.tsx"}, {})
    assert blocked["status"] == "error"
    assert blocked["code"] == "ADAPTIVE_FROZEN"


def test_adaptive_generated_functions_register_into_shared_registry() -> None:
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_defaultspack_functions_registered

    registry = FunctionRegistry()

    class Container:
        def get_or_none(self, name: str):
            if name == "function_registry":
                return registry
            return None

    registered = ensure_defaultspack_functions_registered(Container())
    entry = registry.get("defaultspack:adaptive_onboarding_status")

    assert registered > 0
    assert entry is not None
    assert entry.entrypoint == "template_runner.py:run"
    assert entry.function_dir.name == "function_runtime"
    assert entry.manifest["extensions"]["defaultspack"]["block_module"] == "blocks.adaptive"


def test_context_file_read_search_and_evidence_are_bounded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "app.py").write_text("alpha\nbeta target\ngamma target\n", encoding="utf-8")

    from domain.adaptive.service import dispatch

    read = dispatch(
        "context_file_read",
        {"root": str(workspace), "path": "app.py", "start_line": 2, "max_lines": 1},
        {},
    )
    assert read["status"] == "ok"
    assert read["data"]["line_count"] == 1
    assert read["data"]["lines"][0]["line"] == 2

    search = dispatch("context_code_search", {"root": str(workspace), "query": "target", "max_matches": 1}, {})
    assert search["status"] == "ok"
    assert search["data"]["count"] == 1
    assert search["data"]["truncated"] is True

    evidence = dispatch("context_evidence", {"root": str(workspace), "items": [{"path": "app.py", "start_line": 1, "max_lines": 2}]}, {})
    assert evidence["status"] == "ok"
    assert evidence["data"]["bundle_id"].startswith("ev_")


def test_prepared_actions_redact_secret_and_lease_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import dispatch

    prepared = dispatch(
        "prepared_action_prepare",
        {"profile_id": "coding", "operation": "webhook.create", "arguments": {"shared_secret": "raw"}},
        {},
    )
    assert prepared["status"] == "ok"
    action = prepared["data"]["prepared_action"]
    assert action["display_args"]["shared_secret"] == "[REDACTED]"

    lease = dispatch("lease_acquire", {"profile_id": "coding", "resource": "src/App.tsx", "owner": "agent"}, {})
    assert lease["status"] == "ok"
    released = dispatch("lease_release", {"profile_id": "coding", "id": lease["data"]["lease"]["id"]}, {})
    assert released["status"] == "ok"
    assert released["data"]["lease"]["status"] == "released"
