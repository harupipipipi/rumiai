from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"


IDENT = r"[A-Za-z_$][\w$]*"


def _has_rehydrated_catalog_action(bundle: str) -> bool:
    if "trustedComposerActionForWidget" in bundle:
        return True
    return bool(
        re.search(
            rf"function {IDENT}\({IDENT},{IDENT}\)\{{"
            rf"let {IDENT}={IDENT}\.sourceItemId\|\|{IDENT}\.id,"
            rf"{IDENT}={IDENT}\.find\({IDENT}=>{IDENT}\.id==={IDENT}\),"
            rf"{IDENT}={IDENT}\?{IDENT}\({IDENT}\):null;"
            rf"if\(!\(!{IDENT}\|\|!{IDENT}\|\|{IDENT}!=={IDENT}\.widgetKind\)\)"
            rf"return {IDENT}\.ui\?\.composer_action\}}",
            bundle,
        )
    )


def _has_trusted_action_precedence(bundle: str) -> bool:
    if "trustedComposerActionForWidget(u," in bundle and '((u.action?.type)==="call_endpoint"?void 0:u.action)' in bundle:
        return True
    return bool(
        re.search(
            rf"let {IDENT}={IDENT}\({IDENT},{IDENT}\)\?\?"
            rf"\({IDENT}\.action\?\.type===`call_endpoint`\?void 0:{IDENT}\.action\)",
            bundle,
        )
    )


def _has_endpoint_allowlist_gate(bundle: str) -> bool:
    if "COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey" in bundle and '!e.requires_approval&&Dd(e.endpoint)' in bundle:
        return True
    return bool(
        re.search(
            rf"function {IDENT}\({IDENT}\)\{{return {IDENT}\.type===`call_endpoint`"
            rf"&&!{IDENT}\.requires_approval&&{IDENT}\({IDENT}\.endpoint\)"
            rf"&&{IDENT}\.has\({IDENT}\({IDENT}\)\)\}}",
            bundle,
        )
    )


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert _has_rehydrated_catalog_action(bundle)
    assert _has_trusted_action_precedence(bundle)

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "GET /api/coding/git/status" in bundle
    assert "startsWith(`/api/`)" in bundle or 'startsWith("/api/")' in bundle
    assert "startsWith(`//`)" in bundle or 'startsWith("//")' in bundle
    assert "https?" in bundle
    assert _has_endpoint_allowlist_gate(bundle)
