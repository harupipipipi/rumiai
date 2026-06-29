from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
MIMO_FREE_MODEL = "opencode-zen/mimo-v2.5-free"
MIMO_VISION_MODEL = "google/gemma-4-31b-it"
STUB_MODEL = "stub/default"
MIMO_CONFIG_MODELS = [MIMO_FREE_MODEL, MIMO_VISION_MODEL, STUB_MODEL]


def test_mimo_coding_company_profile_defaults_to_opencode_zen_free_mimo() -> None:
    profile_path = ROOT / "ecosystem" / "rumi_operations_company_pack" / "profiles" / "mimo_coding_company.profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    ai_client = profile["node_settings"]["defaultspack.ai_client"]
    utility_models = ai_client["utility_models"]

    assert ai_client["default_model"] == MIMO_FREE_MODEL
    assert ai_client["model_self_selection"]["allowlist"] == MIMO_CONFIG_MODELS
    assert profile["policy"]["model_allowlist"] == MIMO_CONFIG_MODELS
    assert utility_models["subagent_default"] == MIMO_FREE_MODEL
    assert utility_models["model_router"] == MIMO_FREE_MODEL
    assert utility_models["vision_ocr"] == MIMO_VISION_MODEL
    assert utility_models["tool_selector"] == MIMO_FREE_MODEL
    assert utility_models["prompt_compactor"] == MIMO_FREE_MODEL
    assert utility_models["context_summarizer"] == MIMO_FREE_MODEL
    assert utility_models["fast_reply"] == MIMO_FREE_MODEL


def test_mimo_coding_company_ui_defaults_to_opencode_zen_free_mimo() -> None:
    ui_path = ROOT / "ecosystem" / "rumi_operations_company_pack" / "frontend_extensions" / "operations_company.ui.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8"))

    mimo_section = next(section for section in ui["settings_sections"] if section["id"] == "mimo_coding_company")
    model_field = next(field for field in mimo_section["fields"] if field["id"] == "model_allowlist")

    assert model_field["default"].splitlines() == MIMO_CONFIG_MODELS
