from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _browser_companion_extension_root() -> Path:
    candidates = [
        ROOT / "ecosystem" / "defaultspack" / "browser_extensions" / "rumi_browser_companion",
        ROOT.parent / "browser_extensions" / "rumi_browser_companion",
    ]
    for candidate in candidates:
        if (candidate / "content_script.js").is_file():
            return candidate
    return candidates[0]


def test_form_operator_values_and_submit_actions_are_guarded() -> None:
    content = (_browser_companion_extension_root() / "content_script.js").read_text(encoding="utf-8")
    controller = (
        ROOT
        / "ecosystem"
        / "rumi_default_tools_pack"
        / "domain"
        / "tool"
        / "browser_companion.py"
    ).read_text(encoding="utf-8")

    for needle in (
        "REDACTED_VALUE",
        "include_values_approved",
        "value_redacted",
        "isPasswordValueElement",
        "isSubmitLikeClickTarget",
        "isSubmitLikePressTarget",
        "hasActionApprovalEvidence(command)",
        "target is disabled",
        "target is outside the viewport",
        "target is not topmost",
        "readOnly",
    ):
        assert needle in content

    assert '"include_values"' not in controller[controller.index("allowed = {") : controller.index("return {key: value")]
    assert 'remote_payload["include_values"] = True' in controller
    assert 'remote_payload["include_values_approved"] = True' in controller
    assert 'remote_payload["approval_evidence"] = "tool_server_approval"' in controller
