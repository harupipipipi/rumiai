from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUMI_PKG = ROOT / "rumi_ai_1_10"
if str(RUMI_PKG) not in sys.path:
    sys.path.insert(0, str(RUMI_PKG))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_runtime.operating_profile import (  # noqa: E402
    OperatingProfilePlanStore,
    compile_operating_profile,
    get_builtin_operating_profiles,
    meet_level,
    meet_policy,
    policy_within,
    simulate_scenarios,
)
from core_runtime.operating_profile.constants import MUTATING_ACTION_IDS  # noqa: E402
from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402


def test_compile_is_deterministic_and_builtin_presets_exist():
    answers = {
        "profile_id": "p1",
        "preset": "balanced_local",
        "occupation": "software_engineer",
        "actions": {"terminal": "ask", "external_send": "deny"},
    }

    first = compile_operating_profile(answers).to_dict()
    second = compile_operating_profile(dict(reversed(list(answers.items())))).to_dict()

    assert first == second
    builtins = get_builtin_operating_profiles()
    assert {"discussion_only", "balanced_local", "max_local_autonomy"} <= set(builtins)
    assert builtins["discussion_only"].policy.level_for("local_write").value == "deny"
    assert builtins["max_local_autonomy"].policy.level_for("external_send").value == "deny"


def test_lattice_meet_and_occupation_never_widens_permissions():
    assert meet_level("allow", "ask").value == "ask"
    met = meet_policy({"local_write": "allow", "external_send": "deny"}, {"local_write": "ask", "external_send": "allow"})
    assert met.level_for("local_write").value == "ask"
    assert met.level_for("external_send").value == "deny"

    discussion = compile_operating_profile(
        {"profile_id": "p2", "preset": "discussion_only", "occupation": "software_engineer"}
    )
    assert discussion.policy.level_for("local_write").value == "deny"

    child = compile_operating_profile({"profile_id": "p3", "preset": "max_local_autonomy", "occupation": "child"})
    assert child.policy.level_for("terminal").value == "deny"
    assert child.policy.level_for("external_send").value == "deny"


def test_malicious_pack_recommendation_cannot_widen_answers_or_system_ceiling():
    profile = compile_operating_profile(
        {
            "profile_id": "p4",
            "preset": "max_local_autonomy",
            "actions": {"external_send": "deny"},
        },
        pack_recommendations=[
            {
                "pack_id": "evil_pack",
                "actions": {
                    "external_send": "allow",
                    "terminal": "allow",
                    "local_write": "allow",
                    "__proto__": "allow",
                },
            },
            {"pack_id": "../escape", "actions": {"computer_control": "allow"}},
        ],
        system_ceiling={"terminal": "ask", "external_send": "deny"},
    )

    assert profile.policy.level_for("external_send").value == "deny"
    assert profile.policy.level_for("terminal").value == "ask"
    assert profile.policy.level_for("local_write").value == "allow"
    assert profile.recommended_packs == ["evil_pack"]
    assert any(
        diagnostic["code"] == "pack_contract.pack_id"
        for event in profile.provenance
        if event["source"] == "pack_contract"
        for diagnostic in event["detail"]["diagnostics"]
    )


def test_discussion_only_blocks_mutations_and_max_local_does_not_send_externally():
    discussion = compile_operating_profile({"profile_id": "p5", "preset": "discussion_only"})
    for action_id in sorted(MUTATING_ACTION_IDS):
        assert discussion.policy.level_for(action_id).value == "deny"
    assert discussion.policy.level_for("external_send").value == "deny"

    max_local = compile_operating_profile({"profile_id": "p6", "preset": "max_local_autonomy"})
    assert max_local.policy.level_for("local_write").value == "allow"
    assert max_local.policy.level_for("terminal").value == "allow"
    assert max_local.policy.level_for("external_send").value == "deny"


def test_child_profile_cannot_widen_parent():
    parent = compile_operating_profile({"profile_id": "parent", "preset": "discussion_only"})
    child = compile_operating_profile(
        {"profile_id": "child", "preset": "max_local_autonomy"},
        parent_profile=parent,
    )

    assert child.policy.level_for("local_write").value == "deny"
    assert child.policy.level_for("terminal").value == "deny"
    assert policy_within(child.policy, parent.policy)


def test_scenario_simulator_returns_coding_and_daily_scenarios():
    profile = compile_operating_profile({"profile_id": "p7", "preset": "balanced_local"})
    scenarios = {scenario.scenario_id: scenario.to_dict() for scenario in simulate_scenarios(profile)}

    assert {"coding", "daily"} <= set(scenarios)
    assert "terminal" in scenarios["coding"]["approval_required"]
    assert "external_send" in scenarios["daily"]["blocked"]


def test_signed_plan_apply_and_undo_persist_profile_scoped_files(tmp_path: Path):
    manager = ProfileWorkspaceManager(tmp_path)
    store = OperatingProfilePlanStore(manager)
    initial = compile_operating_profile({"profile_id": "p8", "preset": "discussion_only"})
    first_plan = store.create_plan("p8", initial, reason="initial")
    assert first_plan["signature"]
    store.apply_plan(first_plan)

    target = compile_operating_profile({"profile_id": "p8", "preset": "max_local_autonomy"})
    second_plan = store.create_plan("p8", target, reason="raise local autonomy")
    tampered = dict(second_plan)
    tampered["reason"] = "tampered"
    with pytest.raises(ValueError):
        store.apply_plan(tampered)

    apply_result = store.apply_plan(second_plan)
    active_path = Path(apply_result["path"])
    profile_root = tmp_path / "profiles" / "p8"
    assert active_path == profile_root / "operating_profile" / "active.json"
    assert active_path.is_file()

    reloaded = OperatingProfilePlanStore(ProfileWorkspaceManager(tmp_path))
    assert reloaded.load_active_profile("p8").preset_id == "max_local_autonomy"  # type: ignore[union-attr]

    undo_result = reloaded.undo_plan("p8", second_plan["plan_id"])
    assert Path(undo_result["path"]) == active_path
    restored = reloaded.load_active_profile("p8")
    assert restored is not None
    assert restored.preset_id == "discussion_only"
    assert (profile_root / "operating_profile" / "last_undo.json").is_file()
