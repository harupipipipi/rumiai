from __future__ import annotations

import json
import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
RUMI_ROOT = PACK_ROOT.parents[1]

for path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.function_runtime.manifest_factory import FUNCTION_SPECS, manifest_for  # noqa: E402


MAIN_TEMPLATE = '''from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
RUMI_ROOT = PACK_ROOT.parents[1]
for path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.function_runtime.dispatcher import run_defaultspack_function


def run(context, args):
    return run_defaultspack_function("{function_id}", args, context)
'''

CUSTOM_WRAPPER_FUNCTIONS = {
    # Browser-owned ambient capture exposes a dedicated contract wrapper.
    "ambient_monitor_start",
}


def write_function(spec) -> None:
    function_dir = PACK_ROOT / "functions" / spec.function_id
    function_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = function_dir / "manifest.json"
    main_path = function_dir / "main.py"
    manifest_path.write_text(
        json.dumps(manifest_for(spec), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if spec.function_id in CUSTOM_WRAPPER_FUNCTIONS and main_path.exists():
        return
    main_path.write_text(MAIN_TEMPLATE.format(function_id=spec.function_id), encoding="utf-8")


def main() -> int:
    for spec in FUNCTION_SPECS:
        write_function(spec)
    print(f"generated {len(FUNCTION_SPECS)} defaultspack function wrappers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
