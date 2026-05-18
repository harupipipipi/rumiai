import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    prompts_dir = Path(str(workspace.get("prompts_dir") or "")) if workspace else None
    candidates = []
    if prompts_dir:
        candidates.extend([prompts_dir / "default.system.md", prompts_dir / "system.md"])
    for candidate in candidates:
        if candidate.is_file():
            return ok(
                {
                    "profile_id": data.get("profile_id"),
                    "conversation_id": data.get("conversation_id"),
                    "source": str(candidate),
                    "content": candidate.read_text(encoding="utf-8"),
                }
            )
    return ok(
        {
            "profile_id": data.get("profile_id"),
            "conversation_id": data.get("conversation_id"),
            "source": "defaultspack.empty",
            "content": "",
        }
    )
