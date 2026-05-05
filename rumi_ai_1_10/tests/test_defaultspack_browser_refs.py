from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_snapshot_ref_store_extracts_persists_and_recovers_refs(tmp_path):
    from domain.browser.snapshots import SnapshotRefStore

    store = SnapshotRefStore(tmp_path)
    snapshot = {
        "url": "https://example.test",
        "title": "Checkout",
        "elements": [
            {
                "role": "button",
                "name": "Submit order",
                "text": "Submit order",
                "selector": "#submit",
                "interactive": True,
                "bounds": {"x": 20, "y": 30, "width": 120, "height": 40},
            }
        ],
    }

    refs = store.extract_refs(snapshot)
    assert len(refs) == 1
    assert refs[0]["role"] == "button"
    assert refs[0]["bounds"] == {"x": 20, "y": 30, "width": 120, "height": 40}

    record = store.store_snapshot(session_id="session-1", tab_id="tab-1", snapshot=snapshot)
    saved_ref = store.get_ref(record["refs"][0]["id"])
    assert saved_ref["snapshot_id"] == record["id"]
    assert saved_ref["selector"] == "#submit"

    changed_snapshot = {
        "elements": [
            {
                "role": "button",
                "name": "Submit order",
                "text": "Submit order",
                "selector": "#new-submit",
                "interactive": True,
                "bounds": {"x": 24, "y": 36, "width": 120, "height": 40},
            }
        ]
    }
    recovered = store.recover_ref(saved_ref, snapshot=changed_snapshot)
    assert recovered["selector"] == "#new-submit"
    assert recovered["recovered_from"] == saved_ref["id"]
    assert recovered["recovery_score"] >= 12


def test_browser_ref_action_returns_computer_use_fallback_when_cdp_cannot_execute(tmp_path):
    from domain.browser.sessions import BrowserSessionManager

    class NoWebsocketCdp:
        def evaluate(self, tab_id, script):
            return {"ok": False, "reason": "websocket_dependency_missing"}

    manager = BrowserSessionManager(tmp_path, cdp_client_factory=lambda record: NoWebsocketCdp())
    manager.start_session(session_id="session-1", profile_id="Default", launch=False)
    snapshot = manager.snapshot_store.store_snapshot(
        session_id="session-1",
        tab_id="tab-1",
        snapshot={
            "elements": [
                {
                    "role": "button",
                    "name": "Submit",
                    "text": "Submit",
                    "selector": "#submit",
                    "interactive": True,
                    "bounds": {"x": 20, "y": 30, "width": 100, "height": 40},
                }
            ]
        },
    )

    result = manager.execute_ref_action(
        action="click",
        ref_id=snapshot["refs"][0]["id"],
        session_id="session-1",
        tab_id="tab-1",
    )

    assert result["requires_fallback"] is True
    assert result["fallback_tool"] == "computer_use"
    assert result["fallback_action"] == "click"
    assert result["fallback_payload"]["x"] == 70
    assert result["fallback_payload"]["y"] == 50
