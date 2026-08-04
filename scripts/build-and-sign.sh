#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHER_ROOT="$REPO_ROOT/tobkiri_launcher"

echo "=== Building Tobkiri Launcher (Tauri) ==="
cd "$LAUNCHER_ROOT"
cargo tauri build "$@"

cat <<'EOF'

Tauri signed the macOS app after copying its resources and before creating
the DMG. Do not re-sign the app here: that would leave the DMG containing a
different signature from the post-build .app.
EOF
