import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"

TRUSTED_ACTION_REHYDRATION_RE = re.compile(
    r"function \w+\(\w,\w\)\{let \w=\w\.sourceItemId\|\|\w\.id,"
    r"\w=\w\.find\(\w=>\w\.id===\w\),\w=\w\?\w+\(\w\):null;"
    r"if\(!\(!\w\|\|!\w\|\|\w!==\w\.widgetKind\)\)return "
    r"\w\.ui\?\.composer_action\}"
)
TRUSTED_ACTION_FALLBACK_RE = re.compile(
    r"let \w+=\w+\(\w,\w+\)\?\?\(\w\.action\?\.type===`call_endpoint`"
    r"\?void 0:\w\.action\)"
)
ENDPOINT_ALLOWLIST_RE = re.compile(
    r"function \w+\(\w\)\{return \w\.type===`call_endpoint`"
    r"&&!\w\.requires_approval&&\w+\(\w\.endpoint\)&&\w+\.has\(\w+\(\w\)\)\}"
)


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "trustedComposerActionForWidget" in bundle or TRUSTED_ACTION_REHYDRATION_RE.search(bundle)
    assert "trustedComposerActionForWidget(u," in bundle or TRUSTED_ACTION_FALLBACK_RE.search(bundle)
    assert '((u.action?.type)==="call_endpoint"?void 0:u.action)' in bundle or "action?.type===`call_endpoint`?void 0" in bundle

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "COMPOSER_ENDPOINT_ACTION_ALLOWLIST" in bundle or "new Set([`GET /api/coding/git/status`])" in bundle
    assert "GET /api/coding/git/status" in bundle
    assert "COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey" in bundle or ENDPOINT_ALLOWLIST_RE.search(bundle)
    assert '!e.requires_approval&&Dd(e.endpoint)' in bundle or re.search(r"\.type===`call_endpoint`&&!\w+\.requires_approval&&\w+\(\w+\.endpoint\)", bundle)
