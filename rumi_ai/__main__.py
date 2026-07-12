from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_ROOT = _REPO_ROOT / "tobkiri_runtime"
if str(_LEGACY_ROOT) not in sys.path:
    sys.path.insert(0, str(_LEGACY_ROOT))

from tobkiri_runtime.app import main


if __name__ == "__main__":
    main()
