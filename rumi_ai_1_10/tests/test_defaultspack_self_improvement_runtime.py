from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_mimo_profile_assigns_main_vision_fast_models(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")

    assert runtime.role_map["main"] == "xiaomi-token-plan-sgp/mimo-v2.5-pro"
    assert runtime.role_map["vision"] == "xiaomi-token-plan-sgp/mimo-v2-omni"
    assert runtime.role_map["fast"] == "xiaomi-token-plan-sgp/mimo-v2-flash"


def test_mimo_profile_uses_local_company_profile_role_map(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    status_path = tmp_path / "user_data" / "shared" / "mimo_coding_company" / "codex_manager_status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps(
            {
                "provider": {
                    "models": {
                        "main": "profile/main-current",
                        "vision": "profile/vision-current",
                        "fast": "profile/fast-current",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")

    assert runtime.role_map["main"] == "profile/main-current"
    assert runtime.role_map["vision"] == "profile/vision-current"
    assert runtime.role_map["fast"] == "profile/fast-current"


def test_mimo_profile_status_overrides_stale_company_profile(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    company_path = tmp_path / "ecosystem" / "defaultspack" / "user_data" / "shared" / "companies" / "companies.json"
    company_path.parent.mkdir(parents=True)
    company_path.write_text(
        json.dumps(
            {
                "companies": {
                    "mimo-coding-company": {
                        "metadata": {
                            "main_model": "company/main-stale",
                            "vision_model": "company/vision-stale",
                            "fast_model": "company/fast-stale",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    status_path = tmp_path / "user_data" / "shared" / "mimo_coding_company" / "codex_manager_status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps(
            {
                "provider": {
                    "models": {
                        "main": "status/main-current",
                        "vision": "status/vision-current",
                        "fast": "status/fast-current",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")

    assert runtime.role_map["main"] == "status/main-current"
    assert runtime.role_map["vision"] == "status/vision-current"
    assert runtime.role_map["fast"] == "status/fast-current"


def test_mimo_profile_uses_company_metadata_role_map(tmp_path, monkeypatch):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    company_store = tmp_path / "companies.json"
    company_store.write_text(
        json.dumps(
            {
                "companies": {
                    "mimo-coding-company": {
                        "metadata": {
                            "role_map": {
                                "main": "company/main-current",
                                "vision": "company/vision-current",
                                "fast": "company/fast-current",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(company_store))

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")

    assert runtime.role_map["main"] == "company/main-current"
    assert runtime.role_map["vision"] == "company/vision-current"
    assert runtime.role_map["fast"] == "company/fast-current"


def test_live_self_improvement_defaults_to_current_mimo_models():
    from domain.agent.self_improvement_live_loop import run_live_improvement, run_vision_qa

    assert run_live_improvement.__kwdefaults__["model"] == "xiaomi-token-plan-sgp/mimo-v2.5-pro"
    assert run_vision_qa.__kwdefaults__["model"] == "xiaomi-token-plan-sgp/mimo-v2-omni"


def test_self_improvement_run_defaults_to_current_mimo_main_model(tmp_path, monkeypatch):
    seen: dict[str, object] = {}

    def fake_run_live_improvement(**kwargs):
        seen.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        "domain.agent.self_improvement_live_loop.run_live_improvement",
        fake_run_live_improvement,
    )

    from blocks.agent.self_improvement_run import run

    result = run({"action": "single", "model": "", "workspace_root": str(tmp_path)}, {})

    assert result["status"] == "ok"
    assert seen["model"] == "xiaomi-token-plan-sgp/mimo-v2.5-pro"


def test_self_improvement_run_uses_local_profile_default(tmp_path, monkeypatch):
    seen: dict[str, object] = {}
    status_path = tmp_path / "user_data" / "shared" / "mimo_coding_company" / "codex_manager_status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps({"provider": {"models": {"main": "profile/main", "vision": "profile/vision", "fast": "profile/fast"}}}),
        encoding="utf-8",
    )

    def fake_run_live_improvement(**kwargs):
        seen.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        "domain.agent.self_improvement_live_loop.run_live_improvement",
        fake_run_live_improvement,
    )

    from blocks.agent.self_improvement_run import run

    result = run({"action": "single", "model": "", "workspace_root": str(tmp_path)}, {})

    assert result["status"] == "ok"
    assert seen["model"] == "profile/main"


def test_mimo_vision_role_uses_current_vision_model(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")

    assert runtime.role_map["vision"] == "xiaomi-token-plan-sgp/mimo-v2-omni"


def test_coding_role_rejects_non_tool_call_model():
    from domain.agent.self_improvement_runtime import validate_model_for_role, ModelRoleValidationError

    with pytest.raises(ModelRoleValidationError, match="tool_calls"):
        validate_model_for_role("main", "some/model", {"tool_calls": False})


def test_browser_qa_role_requires_vision_model():
    from domain.agent.self_improvement_runtime import validate_model_for_role, ModelRoleValidationError

    with pytest.raises(ModelRoleValidationError, match="vision"):
        validate_model_for_role("vision", "some/model", {"vision": False})


def test_coding_role_accepts_tool_call_model():
    from domain.agent.self_improvement_runtime import validate_model_for_role

    validate_model_for_role("main", "some/model", {"tool_calls": True})


def test_vision_role_accepts_vision_model():
    from domain.agent.self_improvement_runtime import validate_model_for_role

    validate_model_for_role("vision", "some/model", {"vision": True})


def test_self_improvement_runtime_is_provider_agnostic(tmp_path):
    from domain.agent.self_improvement_runtime import SelfImprovingDefaultspackRuntime

    runtime = SelfImprovingDefaultspackRuntime(
        profile_id="test.custom_provider",
        role_map={
            "main": "custom/main-model",
            "vision": "custom/vision-model",
            "fast": "custom/fast-model",
        },
        workspace_root=tmp_path,
        state_path=tmp_path / "state.json",
    )

    assert runtime.profile_id == "test.custom_provider"
    assert runtime.role_map["main"] == "custom/main-model"
    manifest = runtime.manifest()
    assert manifest["runtime"] == "SelfImprovingDefaultspackRuntime"


def test_self_improvement_runtime_bootstrap_creates_state(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    status = runtime.bootstrap()

    assert status["running"] is True
    assert status["profile_id"] == "defaultspack.mimo_coding_company"

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["running"] is True


def test_self_improvement_runtime_task_lifecycle(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.add_task("t1", "Read file", expected_outcome="file read")
    runtime.start_task("t1")
    runtime.record_tool_call("coding_file_read", {"path": "test.py"})
    runtime.complete_task("t1", {"files_read": ["test.py"]})

    status = runtime.status()
    assert status["completed_count"] == 1
    assert status["failed_count"] == 0
    assert status["last_self_improvement_result"]["files_read"] == ["test.py"]


def test_self_improvement_runtime_fail_task(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.add_task("t2", "Patch file")
    runtime.start_task("t2")
    runtime.fail_task("t2", "permission denied")

    status = runtime.status()
    assert status["failed_count"] == 1
    assert status["current_task"] is None


def test_self_improvement_runtime_pause_resume_stop(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.pause()
    assert runtime.status()["running"] is False

    runtime.resume()
    assert runtime.status()["running"] is True

    runtime.stop()
    status = runtime.status()
    assert status["running"] is False
    assert status["current_task"] is None


def test_self_improvement_runtime_record_test_result(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.record_test_result("pytest tests/test_foo.py", 0, "all passed")

    status = runtime.status()
    assert status["last_test_result"]["exit_code"] == 0
    assert status["last_test_result"]["command"] == "pytest tests/test_foo.py"


def test_self_improvement_runtime_record_commit(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.record_commit("abc1234", "fix: typo", paths=["src/foo.py"])

    status = runtime.status()
    assert status["last_commit"]["commit_hash"] == "abc1234"
    assert status["last_commit"]["paths"] == ["src/foo.py"]


def test_self_improvement_runtime_generate_report(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    runtime.bootstrap()

    runtime.add_task("t1", "Task 1")
    runtime.start_task("t1")
    runtime.complete_task("t1", {"ok": True})
    runtime.add_task("t2", "Task 2")
    runtime.start_task("t2")
    runtime.fail_task("t2", "timeout")

    report = runtime.generate_report()
    assert report["total_tasks"] == 2
    assert report["completed"] == 1
    assert report["failed"] == 1
    assert len(report["friction_points"]) >= 1


def test_self_improvement_runtime_requires_all_roles():
    from domain.agent.self_improvement_runtime import SelfImprovingDefaultspackRuntime, ModelRoleValidationError

    with pytest.raises(ModelRoleValidationError, match="missing role"):
        SelfImprovingDefaultspackRuntime(
            profile_id="test.incomplete",
            role_map={"main": "x"},  # missing vision and fast
        )


def test_mimo_rumi_api_get_allowed(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    assert "rumi_api" in runtime.tool_allowlist


def test_mimo_coding_commit_tool_in_allowlist(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    assert "coding_git_commit" in runtime.tool_allowlist


def test_mimo_profile_manifest_has_role_map(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "state.json")
    manifest = runtime.manifest()

    assert manifest["profile_id"] == "defaultspack.mimo_coding_company"
    assert "main" in manifest["role_map"]
    assert "vision" in manifest["role_map"]
    assert "fast" in manifest["role_map"]
    assert manifest["non_stop"] is True
    assert manifest["can_run_24_7"] is True
