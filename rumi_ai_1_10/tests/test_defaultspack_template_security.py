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


def test_user_data_template_cannot_self_declare_builtin_trust(tmp_path):
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
                "pieces": [{"id": "abs", "kind": "function", "path": "/tmp/handler.py"}],
            }
        ),
        encoding="utf-8",
    )

    result = discover_templates(defaultspack_root=pack_root)

    assert result.templates
    assert result.templates[0].trust_level == TemplateTrustLevel.USER
    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.security.absolute_path" in codes
