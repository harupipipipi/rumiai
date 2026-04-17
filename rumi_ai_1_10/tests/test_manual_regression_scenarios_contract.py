from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
SCENARIO_FILES = sorted(
    (PACKAGE_ROOT / "docs" / "quality_pack").glob("manual_regression_scenarios*.yaml")
)


def _load_all_scenarios() -> list[dict]:
    all_scenarios: list[dict] = []
    for scenario_file in SCENARIO_FILES:
        data = yaml.safe_load(scenario_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data.get("version") == 1
        scenarios = data.get("scenarios")
        assert isinstance(scenarios, list)
        all_scenarios.extend(scenarios)
    return all_scenarios


def test_manual_regression_scenario_files_exist():
    assert len(SCENARIO_FILES) >= 11


def test_manual_regression_scenarios_have_required_fields_and_minimum_count():
    scenarios = _load_all_scenarios()
    assert len(scenarios) >= 1080

    required = {"id", "layer", "risk", "reproduce", "expected", "triage"}
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        missing = required - set(scenario.keys())
        assert not missing, f"scenario missing fields: {missing}"


def test_manual_regression_scenario_ids_are_unique():
    scenarios = _load_all_scenarios()
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids))


def test_manual_regression_scenarios_cover_required_layers():
    layers = {s["layer"] for s in _load_all_scenarios()}
    assert {
        "security-permission",
        "failure-path",
        "frontend-ui",
        "operations-release",
        "data-integrity",
        "observability",
        "recovery",
        "compatibility",
        "performance",
        "user-data-protection",
        "failure-ux",
        "audit-readiness",
    }.issubset(layers)


def test_manual_regression_scenarios_have_layer_minimums():
    counts: dict[str, int] = {}
    for scenario in _load_all_scenarios():
        layer = scenario["layer"]
        counts[layer] = counts.get(layer, 0) + 1

    assert counts.get("security-permission", 0) >= 180
    assert counts.get("failure-path", 0) >= 180
    assert counts.get("frontend-ui", 0) >= 180
    assert counts.get("failure-ux", 0) >= 80
    assert counts.get("audit-readiness", 0) >= 90
    assert counts.get("operations-release", 0) >= 70
    assert counts.get("observability", 0) >= 120
    assert counts.get("data-integrity", 0) >= 45
    assert counts.get("recovery", 0) >= 65
    assert counts.get("compatibility", 0) >= 20
