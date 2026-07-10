import re
from pathlib import Path


SETUP_UI = (
    Path(__file__).resolve().parent.parent
    / "core_runtime"
    / "core_pack"
    / "core_setup"
    / "web"
    / "index.html"
)


def setup_ui_source() -> str:
    """Return the setup-pack landing page source."""
    return SETUP_UI.read_text(encoding="utf-8")


def test_setup_pack_landing_avoids_centered_clipping_layout() -> None:
    """Initial desktop view should top-align and allow natural vertical scroll."""
    source = setup_ui_source()

    assert "place-items: center" not in source
    assert "overflow: hidden;" not in source
    assert "margin: 0 auto;" in source
    assert "grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.65fr)" in source
    assert "min-width: 0;" in source
    assert "overflow-x: clip;" in source
    assert "@media (max-width: 820px)" in source


def test_setup_state_hides_raw_json_behind_debug_disclosure() -> None:
    """The default status panel should render compact copy, not a raw JSON dump."""
    source = setup_ui_source()
    set_status = re.search(
        r"function setStatus\(label, payload, rows, tone = \"neutral\"\) \{(?P<body>.*?)\n    \}",
        source,
        re.S,
    )

    assert set_status is not None
    assert "JSON.stringify(payload, null, 2)" not in set_status.group("body")
    assert "renderInstallSummary(packs, migration)" in source
    assert "Advanced debug state" in source
    assert 'document.createElement("details")' in source


def test_visible_setup_profiles_are_capped_at_five() -> None:
    """The default chooser should present grouped profiles instead of every raw pack."""
    source = setup_ui_source()
    profile_block = re.search(
        r"const PROFILE_CARDS = \[(?P<body>.*?)\n    \];",
        source,
        re.S,
    )

    assert profile_block is not None
    assert profile_block.group("body").count("id:") <= 5
    assert "PROFILE_CARDS.slice(0, 5)" in source
    assert "Advanced custom selection" in source
    assert 'if (assigned.has(packId)) continue;' in source


def test_setup_cards_are_full_clickable_labels() -> None:
    """Selection cards should use label-owned checkboxes for large hit targets."""
    source = setup_ui_source()

    assert 'document.createElement("label")' in source
    assert 'card.className = "pack"' in source
    assert "cursor: pointer;" in source
    assert "min-height: 44px;" in source
    assert "dataset.profilePackIds" in source
    assert 'input.setAttribute("aria-label", "Include " + profile.title)' in source
    assert '.pack:has(input:focus-visible)' in source


def test_group_and_advanced_choices_share_one_selection_model() -> None:
    """Group and individual controls must not submit stale duplicate state."""
    source = setup_ui_source()

    assert "const selectedPackIds = new Set();" in source
    assert "function handleSelectionChange(event)" in source
    assert "selectedPackIds.add(packId)" in source
    assert "selectedPackIds.delete(packId)" in source
    assert 'listEl.addEventListener("change", handleSelectionChange)' in source
    assert "return Array.from(selectedPackIds);" in source


def test_install_action_sends_selected_ids_and_reports_feedback() -> None:
    """Install should post selected setup pack ids and expose pending/result feedback."""
    source = setup_ui_source()

    assert "const selected = selectedSetupPackIds();" in source
    assert 'body: JSON.stringify({ setup_pack_ids: selected })' in source
    assert 'getJson("/api/setup/packs/install"' in source
    assert 'setInstallProgress("pending")' in source
    assert 'setInstallProgress("success")' in source
    assert 'setInstallProgress("error")' in source
    assert 'id="install-progress"' in source
    assert 'id="install-selected" disabled' in source
    assert "const refreshed = await load({ preserveStatus: true, redirect: false });" in source
    assert "if (!refreshed) return;" in source
    assert 'aria-live="polite"' in source
    assert 'setStatus("Installing setup packs…"' in source
    assert 'setStatus("Setup packs installed"' in source
