from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"


def assert_any_contains(bundle: str, *needles: str) -> None:
    assert any(needle in bundle for needle in needles), (
        "expected shipped bundle to contain one of: "
        + ", ".join(repr(needle) for needle in needles)
    )


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "trustedComposerActionForWidget" in bundle
    assert "composer_catalog_drop" in bundle
    assert "sourceItemId" in bundle
    assert_any_contains(
        bundle,
        "trustedComposerActionForWidget(u,",
        "trustedComposerActionForWidget(widget,",
    )
    assert_any_contains(
        bundle,
        '((u.action?.type)==="call_endpoint"?void 0:u.action)',
        "widget.action?.type===`call_endpoint`?void 0:widget.action",
    )
    assert re.search(
        r"\?\?\([^)]*\.action\?\.type===`call_endpoint`\?void 0:[^)]*\.action\)",
        bundle,
    )

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "GET /api/coding/git/status" in bundle
    assert "call_endpoint" in bundle
    assert "requires_approval" in bundle
    assert "COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey" in bundle
    assert_any_contains(
        bundle,
        '!e.requires_approval&&Dd(e.endpoint)',
        "!action.requires_approval&&isSafeLocalEndpoint(action.endpoint)",
    )
    assert re.search(
        r"\.type===`call_endpoint`&&![^.]+\.requires_approval&&[^(]+\([^.]+\.endpoint\)&&[^.]+\.has\(",
        bundle,
    )
