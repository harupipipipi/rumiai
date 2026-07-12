import os
import sys
from pathlib import Path

# Add defaultspack root, its parent (ecosystem), and the workspace root to sys.path
defaultspack_root = Path(__file__).resolve().parent
sys.path.insert(0, str(defaultspack_root))
sys.path.insert(0, str(defaultspack_root.parent))
sys.path.insert(0, str(defaultspack_root.parent.parent))

from transport.http import start_http_server

if __name__ == "__main__":
    print("Starting defaultspack HTTP server in standalone mode on port 8766...")
    start_http_server(None)
