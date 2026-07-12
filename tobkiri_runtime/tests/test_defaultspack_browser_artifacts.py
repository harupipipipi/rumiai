from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_artifact_store_persists_screenshot_text_console_and_url(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_BROWSER_ARTIFACTS_PATH", str(tmp_path / "artifacts.jsonl"))

    from domain.browser.browser_artifacts import BrowserArtifactStore

    store = BrowserArtifactStore()
    artifact = store.record(
        "browser_screenshot",
        {
            "session_id": "session-1",
            "url": "file:///tmp/fixture.html",
            "text": "fixture text",
            "console_logs": [{"level": "log", "text": "ready"}],
            "data_url": "data:image/png;base64,AAAA",
            "image_size": {"width": 320, "height": 200},
        },
    )

    listed = BrowserArtifactStore().list(session_id="session-1")

    assert listed[0]["artifact_id"] == artifact["artifact_id"]
    assert listed[0]["url"] == "file:///tmp/fixture.html"
    assert listed[0]["text"] == "fixture text"
    assert listed[0]["console"][0]["text"] == "ready"
    assert listed[0]["screenshot"]["image_size"]["width"] == 320


def test_browser_artifacts_block_lists_persisted_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_BROWSER_ARTIFACTS_PATH", str(tmp_path / "artifacts.jsonl"))

    from blocks.browser.artifacts import run as artifacts_run
    from domain.browser.browser_artifacts import BrowserArtifactStore

    BrowserArtifactStore().record("browser_open_url", {"session_id": "session-2", "url": "http://localhost:8000"})

    result = artifacts_run({"session_id": "session-2"}, {})

    assert result["status"] == "ok"
    assert result["data"]["count"] == 1
    assert result["data"]["artifacts"][0]["action"] == "browser_open_url"
