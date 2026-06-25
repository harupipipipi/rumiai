from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import (  # noqa: E402
    TemplateTrustLevel,
    assess_template_security,
    discover_templates,
    parse_template,
)


def test_non_builtin_templates_reject_absolute_paths_parent_segments_and_shell_handlers():
    result = parse_template(
        {
            "id": "unsafe.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "trust_level": "user",
            "pieces": [
                {"id": "abs", "kind": "function", "path": "/tmp/handler.py"},
                {"id": "parent", "kind": "function", "entrypoint": "../handler.py"},
                {"id": "shell", "kind": "function", "handler": "bash -lc run"},
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.security.absolute_path" in codes
    assert "template.security.parent_traversal" in codes
    assert "template.security.shell_like_handler" in codes
    assert not result.ok


def test_builtin_templates_are_exempt_from_path_security_diagnostics():
    result = parse_template(
        {
            "id": "builtin.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "trust_level": "builtin",
            "pieces": [{"id": "builtin", "kind": "function", "path": "/opt/rumi/handler.py"}],
        }
    )

    assert result.template is not None
    assert assess_template_security(result.template) == []
    assert result.ok


def test_user_template_cannot_self_promote_to_builtin(tmp_path):
    pack_root = tmp_path / "defaultspack"
    template_path = pack_root / "user_data" / "shared" / "templates" / "spoof" / "template.json"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        json.dumps(
            {
                "id": "user.spoof",
                "kind": "pack",
                "version": "1.0.0",
                "status": "active",
                "trust_level": "builtin",
                "pieces": [
                    {"id": "abs", "kind": "function", "path": "/tmp/handler.py"},
                    {"id": "shell", "kind": "function", "handler": "bash -lc run"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = discover_templates(defaultspack_root=pack_root)

    assert result.templates
    assert result.templates[0].trust_level == TemplateTrustLevel.USER
    assert result.templates[0].metadata["declared_trust_level"] == "builtin"
    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.security.absolute_path" in codes
    assert "template.security.shell_like_handler" in codes


def test_bare_root_named_defaultspack_templates_does_not_infer_builtin_trust(tmp_path):
    spoof_root = tmp_path / "attacker" / "defaultspack" / "templates"
    template_path = spoof_root / "spoof" / "template.json"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        json.dumps(
            {
                "id": "path.spoof",
                "kind": "pack",
                "version": "1.0.0",
                "status": "active",
                "trust_level": "builtin",
                "pieces": [
                    {"id": "abs", "kind": "function", "path": "/tmp/handler.py"},
                    {"id": "shell", "kind": "function", "handler": "shell:echo nope"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = discover_templates([spoof_root])

    assert result.templates
    assert result.templates[0].trust_level == TemplateTrustLevel.USER
    assert result.templates[0].metadata["declared_trust_level"] == "builtin"
    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.security.absolute_path" in codes
    assert "template.security.shell_like_handler" in codes
