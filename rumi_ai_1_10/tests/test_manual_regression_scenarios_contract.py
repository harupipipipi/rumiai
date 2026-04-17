from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
SCENARIO_FILE = PACKAGE_ROOT / "docs" / "quality_pack" / "manual_regression_scenarios.yaml"


def test_manual_regression_scenarios_file_exists():
    assert SCENARIO_FILE.exists()


def test_manual_regression_scenarios_have_required_fields_and_minimum_count():
    data = yaml.safe_load(SCENARIO_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("version") == 1
    scenarios = data.get("scenarios")
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 60

    required = {"id", "layer", "risk", "reproduce", "expected", "triage"}
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        missing = required - set(scenario.keys())
        assert not missing, f"scenario missing fields: {missing}"


def test_manual_regression_scenario_ids_are_unique():
    data = yaml.safe_load(SCENARIO_FILE.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids))


def test_manual_regression_scenarios_cover_three_layers():
    data = yaml.safe_load(SCENARIO_FILE.read_text(encoding="utf-8"))
    layers = {s["layer"] for s in data["scenarios"]}
    assert {"security-permission", "failure-path", "frontend-ui"}.issubset(layers)
