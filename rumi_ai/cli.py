from pathlib import Path
import sys


def _ensure_runtime_on_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    runtime_root = repo_root / "rumi_ai_1_10"
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))


def main() -> None:
    _ensure_runtime_on_path()
    from rumi_ai_1_10.app import main as runtime_main

    runtime_main()


if __name__ == "__main__":
    main()
