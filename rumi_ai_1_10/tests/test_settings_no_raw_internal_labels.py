from scripts.migrate_settings_control_center import migrate


def test_migrate_removes_mimo_raw_label():
    raw = {"settings": {"model_preset": {"category": "model", "label": "mimo"}}}
    migrated = migrate(raw)
    setting = migrated["settings"]["model_preset"]
    assert setting["section"] == "models_api"
    assert setting["display_name"] == "Mimo model preset"
    assert setting["legacy_label"] == "mimo"


def test_gradient_moves_to_workspace_ui():
    raw = {"settings": {"computer_use_gradient": {"category": "tools", "label": "computer_use_gradient"}}}
    migrated = migrate(raw)
    setting = migrated["settings"]["computer_use_gradient"]
    assert setting["section"] == "workspace_ui"
    assert setting["display_name"] == "Automation visual indicator"
