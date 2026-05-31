#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Rumi AI"
APP_BUNDLE="$REPO_ROOT/rumi_viewer/src-tauri/target/release/bundle/macos/$APP_NAME.app"

echo "=== Building Rumi AI (Tauri) ==="
cd "$REPO_ROOT/rumi_viewer"
cargo tauri build "$@"

echo ""
echo "=== Re-signing $APP_NAME.app (ad-hoc with --deep) ==="
codesign --force --deep --sign - "$APP_BUNDLE"

echo ""
echo "=== Verifying signature ==="
codesign -v "$APP_BUNDLE"

echo ""
echo "=== Done ==="
echo "Bundle: $APP_BUNDLE"