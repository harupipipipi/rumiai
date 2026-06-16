from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_APP = REPO_ROOT / "ecosystem" / "defaultspack" / "ui" / "shell-app.js"


def test_shipped_composer_bundle_rehydrates_catalog_actions():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "trustedComposerActionForWidget" in bundle
    assert "composer_catalog_drop" in bundle
    assert "sourceItemId" in bundle
    trusted_action_match = re.search(
        r"function ([A-Za-z_$][\w$]*)\([^)]*\).*?s\(\1,\"trustedComposerActionForWidget\"\);"
        r"\1\.__rumiBundleHardeningMarker=\"trustedComposerActionForWidget\"",
        bundle,
    )
    assert trusted_action_match
    trusted_action_name = trusted_action_match.group(1)
    handle_widget_match = re.search(r"[A-Za-z_$][\w$]*=s\([^=]+=>.*?,\"handleWidgetAction\"\)", bundle)
    assert handle_widget_match
    handle_widget_fragment = handle_widget_match.group(0)
    assert f"{trusted_action_name}(" in handle_widget_fragment
    assert re.search(
        r"\?\?\(\(\([^)]*\.action\)==null\?void 0:[^)]*\.type\)===\"call_endpoint\"\?void 0:[^)]*\.action\)",
        handle_widget_fragment,
    )

    # Regression guard for the stale bundle vulnerability: the shipped composer
    # must not execute a dropped widget's serialized action directly.
    assert "Yu=u=>{const b=u.action" not in bundle


def test_shipped_composer_bundle_keeps_endpoint_allowlist():
    bundle = SHELL_APP.read_text(encoding="utf-8")

    assert "GET /api/coding/git/status" in bundle
    assert "call_endpoint" in bundle
    assert "requires_approval" in bundle
    assert re.search(
        r"function [A-Za-z_$][\w$]*\(([A-Za-z_$][\w$]*)\)\{return "
        r"\1\.type===\"call_endpoint\"&&!\1\.requires_approval&&"
        r"[A-Za-z_$][\w$]*\(\1\.endpoint\)&&[A-Za-z_$][\w$]*\.has\([A-Za-z_$][\w$]*\(\1\)\)"
        r"\}s\([A-Za-z_$][\w$]*,\"canExecuteComposerEndpointAction\"\)",
        bundle,
    )
    assert re.search(
        r"function [A-Za-z_$][\w$]*\(([A-Za-z_$][\w$]*)\)\{return "
        r"\1\.startsWith\(\"/api/\"\)&&!\1\.startsWith\(\"//\"\)&&!/\^https\?:\\\/\\\/.*?/i\.test\(\1\)"
        r"\}s\([A-Za-z_$][\w$]*,\"isSafeLocalEndpoint\"\)",
        bundle,
    )
