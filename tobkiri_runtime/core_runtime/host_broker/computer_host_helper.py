from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _ensure_import_path() -> None:
    base = Path(__file__).resolve().parents[2]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))


def main() -> int:
    _ensure_import_path()
    os.environ["RUMI_COMPUTER_HOST_INTERNAL"] = "1"

    request = json.loads(sys.stdin.read() or "{}")
    action = str(request.get("function_id") or "").strip()
    payload = dict(request.get("args") or {})
    viewer_host_approved = bool(request.get("viewer_host_approved"))

    try:
        if action.startswith("browser."):
            from ecosystem.rumi_browser_host_service_pack.runtime.runner import (
                run_browser_host_action,
            )

            result = run_browser_host_action(
                action,
                payload,
                viewer_host_approved=viewer_host_approved,
            )
        else:
            from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
                BrowserComputerController,
            )

            artifact_root = _validated_artifact_root(request.get("artifact_root"))
            result = BrowserComputerController(artifact_root=artifact_root).run(
                action,
                payload,
                yolo_mode=viewer_host_approved,
            )
    except ValueError as exc:
        print(
            json.dumps(
                {"ok": False, "error_code": "INVALID_ARTIFACT_ROOT", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:  # pragma: no cover - caller converts to broker error
        print(json.dumps({"ok": False, "error_code": "VIEWER_HOST_FAILED", "error": str(exc)}, ensure_ascii=False))
        return 0

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


def _validated_artifact_root(raw_value: object) -> Path | None:
    if raw_value is None:
        return None
    value = str(raw_value or "").strip()
    if not value:
        return None
    candidate = Path(value).expanduser().resolve()
    if candidate.name != "computer":
        raise ValueError("artifact_root must end with tools/computer.")
    tools_dir = candidate.parent
    workspace_dir = tools_dir.parent
    conversation_dir = workspace_dir.parent
    if tools_dir.name != "tools" or workspace_dir.name != "workspace" or not conversation_dir.name:
        raise ValueError("artifact_root must be inside a conversation workspace tools/computer directory.")
    for root in _allowed_conversation_roots():
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) == 4 and relative.parts[1:] == ("workspace", "tools", "computer"):
            return candidate
    raise ValueError("artifact_root is outside the allowed conversation workspace roots.")


def _allowed_conversation_roots() -> list[Path]:
    roots: list[Path] = []
    override = str(os.environ.get("RUMI_DEFAULTSPACK_CHAT_STORE_PATH") or "").strip()
    if override:
        roots.append(Path(override).expanduser().resolve().parent / "conversations")
    base = Path(__file__).resolve().parents[2]
    roots.append(base / "ecosystem" / "defaultspack" / "user_data" / "shared" / "chat" / "conversations")

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = root.resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resolved)
    return deduped


if __name__ == "__main__":
    raise SystemExit(main())
