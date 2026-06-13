from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "trustedComposerActionForWidget" in bundle
    assert "trustedComposerActionForWidget(u," in bundle
    assert '((u.action?.type)==="call_endpoint"?void 0:u.action)' in bundle

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "COMPOSER_ENDPOINT_ACTION_ALLOWLIST" in bundle
    assert "GET /api/coding/git/status" in bundle
    assert "COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey" in bundle
    assert '!e.requires_approval&&Dd(e.endpoint)' in bundle
