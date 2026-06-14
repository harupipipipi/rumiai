from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "trustedComposerActionForWidget" in bundle
    assert "composer_catalog_drop" in bundle
    assert "sourceItemId||" in bundle
    assert re.search(
        r"\?\?\(?\(?[A-Za-z_$][\w$]*\.action\?\.type\)?===[`\"]call_endpoint[`\"]\?void 0:[A-Za-z_$][\w$]*\.action\)?",
        bundle,
    )

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "GET /api/coding/git/status" in bundle
    assert re.search(
        r"type===[`\"]call_endpoint[`\"]&&![A-Za-z_$][\w$]*\.requires_approval&&[A-Za-z_$][\w$]*\([A-Za-z_$][\w$]*\.endpoint\)&&[A-Za-z_$][\w$]*\.has\([A-Za-z_$][\w$]*\([A-Za-z_$][\w$]*\)\)",
        bundle,
    )
