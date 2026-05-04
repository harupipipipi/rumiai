from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], *, timeout: float = 10.0) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"body": raw}
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"body": raw}
        return {"ok": False, "status": exc.code, "body": parsed}
    except Exception as exc:
        return {"ok": False, "status": 0, "body": {"error": str(exc)}}
