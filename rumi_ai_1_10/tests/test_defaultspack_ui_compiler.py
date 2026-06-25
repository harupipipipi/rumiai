from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from domain.ui_compiler import (  # noqa: E402
    ComplexitySignals,
    LeafBudget,
    RecursiveUIPlanner,
    UICompilerArtifactStore,
    budget_violations,
    calculate_complexity,
    compile_ui_plan,
)


def _inbox_tree() -> dict:
    return {
        "id": "inbox",
        "purpose": "Process unresolved conversations quickly.",
        "density": "compact",
        "children": [
            {
                "id": "inbox-toolbar",
                "purpose": "Filter the conversation set.",
                "density": "compact",
                "importance": "secondaryRegion",
                "complexity": {
                    "uniqueVisualRoles": 6,
                    "interactiveControls": 3,
                    "meaningfulStates": 2,
                    "asyncMutations": 0,
                    "responsiveTopologies": 1,
                    "specialLayoutAlgorithms": 0,
                },
                "allowedPrimitives": ["Button", "SegmentedControl", "SearchField"],
                "visibleActionBudget": 3,
            },
            {
                "id": "reply-composer",
                "purpose": "Send a safe reply to the selected conversation.",
                "primaryPerceptualTask": "Understand draft state and send readiness.",
                "density": "comfortable",
                "importance": "primaryRegion",
                "layoutEnvelope": {
                    "minWidth": 280,
                    "preferredWidth": 560,
                    "maxWidth": 760,
                    "heightBehavior": "content",
                    "mobileBehavior": "sticky-bottom",
                },
                "complexity": {
                    "uniqueVisualRoles": 18,
                    "interactiveControls": 7,
                    "meaningfulStates": 6,
                    "asyncMutations": 2,
                    "responsiveTopologies": 2,
                    "specialLayoutAlgorithms": 0,
                },
                "inputs": ["draft", "isSending", "error", "attachments"],
                "events": ["onDraftChange", "onSend", "onRetry", "onAttach"],
                "requiredStates": ["empty", "editing", "sending", "error", "sent"],
                "allowedPrimitives": ["Button", "TextArea", "InlineAlert", "IconButton"],
                "visibleActionBudget": 3,
                "splitHints": [
                    {
                        "id": "reply-composer-draft-input",
                        "purpose": "Capture and review the reply draft.",
                        "density": "comfortable",
                        "importance": "primaryRegion",
                        "layoutEnvelope": {"minWidth": 280, "preferredWidth": 560, "maxWidth": 760},
                        "complexity": {
                            "uniqueVisualRoles": 6,
                            "interactiveControls": 1,
                            "meaningfulStates": 3,
                            "asyncMutations": 0,
                            "responsiveTopologies": 2,
                            "specialLayoutAlgorithms": 0,
                        },
                        "inputs": ["draft"],
                        "events": ["onDraftChange"],
                        "requiredStates": ["empty", "editing", "sending"],
                        "allowedPrimitives": ["TextArea"],
                        "visibleActionBudget": 1,
                    },
                    {
                        "id": "reply-composer-send-controls",
                        "purpose": "Expose send, retry, and readiness actions.",
                        "density": "comfortable",
                        "importance": "primaryRegion",
                        "layoutEnvelope": {"minWidth": 280, "preferredWidth": 560, "maxWidth": 760},
                        "complexity": {
                            "uniqueVisualRoles": 5,
                            "interactiveControls": 3,
                            "meaningfulStates": 2,
                            "asyncMutations": 1,
                            "responsiveTopologies": 2,
                            "specialLayoutAlgorithms": 0,
                        },
                        "inputs": ["isSending", "error"],
                        "events": ["onSend", "onRetry"],
                        "requiredStates": ["editing", "sending", "error"],
                        "allowedPrimitives": ["Button", "InlineAlert"],
                        "visibleActionBudget": 3,
                    },
                    {
                        "id": "reply-composer-attachment-tray",
                        "purpose": "Show attachment state without crowding send controls.",
                        "density": "comfortable",
                        "importance": "secondaryRegion",
                        "layoutEnvelope": {"minWidth": 280, "preferredWidth": 560, "maxWidth": 760},
                        "complexity": {
                            "uniqueVisualRoles": 4,
                            "interactiveControls": 1,
                            "meaningfulStates": 2,
                            "asyncMutations": 0,
                            "responsiveTopologies": 2,
                            "specialLayoutAlgorithms": 0,
                        },
                        "inputs": ["attachments"],
                        "events": ["onAttach"],
                        "requiredStates": ["empty", "editing"],
                        "allowedPrimitives": ["IconButton", "InlineAlert"],
                        "visibleActionBudget": 1,
                    },
                ],
            },
        ],
    }


def test_complexity_formula_and_budget_violations() -> None:
    signals = ComplexitySignals(
        unique_visual_roles=10,
        interactive_controls=3,
        meaningful_states=4,
        async_mutations=1,
        responsive_topologies=2,
        special_layout_algorithms=1,
    )

    assert calculate_complexity(signals) == 41
    assert budget_violations(signals, LeafBudget(max_complexity=40)) == ["complexity"]


def test_recursive_planner_uses_split_hints_for_oversized_leaf() -> None:
    plan = RecursiveUIPlanner().plan(_inbox_tree(), run_id="inbox-demo")
    contract_by_id = {contract.id: contract for contract in plan.contracts()}

    assert plan.to_dict()["summary"] == {
        "leafCount": 4,
        "contractCount": 4,
        "overBudgetLeafCount": 0,
    }
    assert set(contract_by_id) == {
        "inbox-toolbar",
        "reply-composer-draft-input",
        "reply-composer-send-controls",
        "reply-composer-attachment-tray",
    }
    send_contract = contract_by_id["reply-composer-send-controls"]
    assert send_contract.candidate_count == 2
    assert send_contract.visible_action_budget == 3
    assert send_contract.layout_envelope.preferred_width == 560
    assert not plan.over_budget_leaves()


def test_recursive_planner_heuristically_splits_budget_overflow() -> None:
    page = {
        "id": "dense-board",
        "purpose": "Coordinate many work items in one operational page.",
        "importance": "primaryRegion",
        "complexity": {
            "uniqueVisualRoles": 34,
            "interactiveControls": 11,
            "meaningfulStates": 10,
            "asyncMutations": 3,
            "responsiveTopologies": 4,
            "specialLayoutAlgorithms": 2,
        },
        "inputs": ["query", "filters", "selection"],
        "events": ["onFilter", "onSelect", "onBulkApply"],
        "requiredStates": ["empty", "loading", "loaded", "error", "saving"],
        "allowedPrimitives": ["Button", "Select", "Table", "InlineAlert"],
    }

    plan = RecursiveUIPlanner().plan(page, run_id="dense-board")
    leaf_ids = {leaf.node.id for leaf in plan.root.leaves()}

    assert len(leaf_ids) >= 4
    assert "dense-board-interaction-region" in leaf_ids
    assert not plan.over_budget_leaves()


def test_artifact_store_writes_constitution_blueprint_contracts_and_report(tmp_path: Path) -> None:
    plan = RecursiveUIPlanner().plan(_inbox_tree(), run_id="inbox-artifacts")
    store = UICompilerArtifactStore(tmp_path / ".rumi" / "ui")

    artifacts = store.save_plan(plan)

    assert Path(artifacts["constitution"]).is_file()
    assert Path(artifacts["blueprint"]).is_file()
    assert Path(artifacts["report"]).is_file()
    assert len(artifacts["contracts"]) == 4
    report = json.loads(Path(artifacts["report"]).read_text(encoding="utf-8"))
    assert report["summary"]["overBudgetLeafCount"] == 0

    with pytest.raises(ValueError):
        store.save_candidate_manifest(node_id="../reply-composer", candidate_id="a", manifest={})


def test_compile_plan_does_not_trust_client_supplied_approved_for_persistence(tmp_path: Path) -> None:
    denied = compile_ui_plan(
        {
            "ui_tree": _inbox_tree(),
            "run_id": "client-approved",
            "persist": True,
            "approved": True,
            "artifact_root": str(tmp_path),
        },
        {},
    )

    assert denied["status"] == "error"
    assert denied["error"]["code"] == "APPROVAL_REQUIRED"
    assert not (tmp_path / ".rumi" / "ui" / "blueprints" / "client-approved.json").exists()

    allowed = compile_ui_plan(
        {
            "ui_tree": _inbox_tree(),
            "run_id": "approved-context",
            "persist": True,
            "artifact_root": str(tmp_path),
        },
        {"profile_policy": {"yolo_mode": True}},
    )

    assert allowed["status"] == "ok"
    assert (tmp_path / ".rumi" / "ui" / "blueprints" / "approved-context.json").is_file()


def test_ui_compile_plan_tool_is_registered_and_executes_with_approval_context(tmp_path: Path) -> None:
    ToolRegistry._instance = None
    tool = ToolRegistry().get("tool_ui_compile_plan")

    result = ToolExecutor().execute(
        "tool_ui_compile_plan",
        {
            "ui_tree": _inbox_tree(),
            "run_id": "tool-run",
            "persist": True,
            "artifact_root": str(tmp_path),
        },
        {
            "profile_policy": {"yolo_mode": True},
            "conversation_workspace_dir": str(tmp_path),
            "principal_id": "defaultspack",
        },
    )

    assert tool is not None
    assert tool["execution"]["handler"] == "domain.ui_compiler.tool:ui_compile_plan"
    assert result["is_error"] is False
    assert result["widget"]["type"] == "ui_compile_plan"
    assert result["widget"]["summary"]["contractCount"] == 4
    assert (tmp_path / ".rumi" / "ui" / "blueprints" / "tool-run.json").is_file()
