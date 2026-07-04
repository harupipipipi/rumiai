from pathlib import Path
import re


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
    assert "grid-template-columns: minmax(320px, 1fr) minmax(280px, 0.82fr)" in source
    assert "overflow-x: hidden;" in source


def test_setup_state_hides_raw_json_behind_debug_disclosure() -> None:
    """The default status panel should render compact copy, not a raw JSON dump."""
    source = setup_ui_source()
    set_status = re.search(
        r"function setStatus\(label, payload, rows\) \{(?P<body>.*?)\n    \}",
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


def test_setup_cards_are_full_clickable_labels() -> None:
    """Selection cards should use label-owned checkboxes for large hit targets."""
    source = setup_ui_source()

    assert 'document.createElement("label")' in source
    assert 'card.className = "pack"' in source
    assert "cursor: pointer;" in source
    assert "min-height: 44px;" in source
    assert "dataset.profilePackIds" in source


def test_install_action_sends_selected_ids_and_reports_feedback() -> None:
    """Install should post selected setup pack ids and expose pending/result feedback."""
    source = setup_ui_source()

    assert "const selected = selectedSetupPackIds();" in source
    assert 'body: JSON.stringify({ setup_pack_ids: selected })' in source
    assert 'getJson("/api/setup/packs/install"' in source
    assert "installButton.disabled = true;" in source
    assert "installButton.disabled = false;" in source
    assert 'setStatus("Installing setup packs…"' in source
    assert 'setStatus("Setup packs installed"' in source
