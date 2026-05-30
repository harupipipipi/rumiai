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

    try:
        from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

        result = BrowserComputerController().run(action, payload, yolo_mode=False)
    except Exception as exc:  # pragma: no cover - caller converts to broker error
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 0

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
