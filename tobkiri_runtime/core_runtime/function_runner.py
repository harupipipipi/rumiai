"""
function_runner.py - JSON 入力で Python callable を実行する runner
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Avoid shadowing stdlib modules like `types` when this file is executed directly
# from inside the core_runtime package directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0]) == _SCRIPT_DIR:
    sys.path.pop(0)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_configure_utf8_stdio()


def _emit_error(message: str, error_type: str) -> None:
    print(json.dumps({"error": message, "error_type": error_type}))


def _load_input(args: argparse.Namespace) -> Dict[str, Any]:
    if args.input_file:
        raw = Path(args.input_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Runner payload must be a JSON object")
    return payload


def _load_callable(module_path: str, callable_name: str):
    target = Path(module_path)
    if not target.is_file():
        raise FileNotFoundError(f"Module file not found: {module_path}")

    cwd = os.getcwd()
    module_dir = str(target.parent.resolve())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    spec = importlib.util.spec_from_file_location("rumi_runtime_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["rumi_runtime_target"] = module
    spec.loader.exec_module(module)

    fn = getattr(module, callable_name, None)
    if fn is None:
        raise AttributeError(f"Callable '{callable_name}' not found")
    return fn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Python callable from JSON input.")
    parser.add_argument("--input-file", help="Path to JSON input file")
    parsed = parser.parse_args()

    try:
        payload = _load_input(parsed)
        module_path = payload.get("module_path", "")
        callable_name = payload.get("callable_name", "")
        context = payload.get("context", {})
        args = payload.get("args", {})

        if not module_path:
            _emit_error("No module_path specified", "config_error")
            return 1
        if not callable_name:
            _emit_error("No callable_name specified", "config_error")
            return 1

        fn = _load_callable(module_path, callable_name)
        result = fn(context, args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    except json.JSONDecodeError as exc:
        _emit_error(f"Invalid input JSON: {exc}", "json_error")
        return 1
    except FileNotFoundError as exc:
        _emit_error(str(exc), "file_not_found")
        return 1
    except AttributeError as exc:
        _emit_error(str(exc), "func_not_found")
        return 1
    except RuntimeError as exc:
        _emit_error(str(exc), "load_error")
        return 1
    except Exception as exc:
        _emit_error(str(exc), type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
