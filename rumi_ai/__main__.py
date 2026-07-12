from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME_ROOT = _REPO_ROOT / "rumi_ai_1_10"
if str(_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_ROOT))

from tobkiri.runtime import main


if __name__ == "__main__":
    main()
