"""
defaultspack.cli — Entry point for `python -m defaultspack.cli`.

Usage:
    python -m defaultspack.cli                     # interactive mode
    python -m defaultspack.cli --message "Hello"   # one-shot mode
    echo "Hello" | python -m defaultspack.cli      # pipe mode
    python -m defaultspack.cli --json              # JSON output mode
    python -m defaultspack.cli --http              # HTTP backend mode
"""

import sys
import os

# Ensure pack root is on sys.path so that `blocks`, `transport`, `domain`
# are importable regardless of how the module is launched.
_pack_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pack_root not in sys.path:
    sys.path.insert(0, _pack_root)

from transport.cli import main as cli_main


def main():
    cli_main()


if __name__ == "__main__":
    main()
