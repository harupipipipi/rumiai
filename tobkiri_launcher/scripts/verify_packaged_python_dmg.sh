#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' 'Usage: verify_packaged_python_dmg.sh --dmg PATH --target TARGET --expected-manifest-sha256 SHA256' >&2
}

dmg=''
target=''
expected_manifest=''
while (($# > 0)); do
  case "$1" in
    --dmg) (($# >= 2)) || { usage; exit 2; }; dmg=$2; shift 2 ;;
    --target) (($# >= 2)) || { usage; exit 2; }; target=$2; shift 2 ;;
    --expected-manifest-sha256)
      (($# >= 2)) || { usage; exit 2; }
      expected_manifest=$2
      shift 2
      ;;
    *) usage; exit 2 ;;
  esac
done

[[ -f "$dmg" && -n "$target" && "$expected_manifest" =~ ^[0-9a-f]{64}$ ]] || {
  usage
  exit 2
}
command -v hdiutil >/dev/null 2>&1 || {
  printf 'hdiutil is required to verify the packaged Python DMG\n' >&2
  exit 1
}

script_dir=$(cd "$(dirname "$0")" && pwd -P)
repo_root=$(cd "$script_dir/../.." && pwd -P)
mountpoint=$(mktemp -d "${TMPDIR:-/tmp}/tobkiri-dmg-verify.XXXXXX")
attached=0
cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if ((attached == 1)); then
    hdiutil detach "$mountpoint" >/dev/null || status=1
  fi
  rmdir "$mountpoint" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

hdiutil attach -readonly -nobrowse -mountpoint "$mountpoint" "$dmg" >/dev/null
attached=1
app_bundle=$(find "$mountpoint" -maxdepth 1 -type d -name '*.app' -print -quit)
[[ -n "$app_bundle" ]] || {
  printf 'DMG contains no application bundle\n' >&2
  exit 1
}
/usr/bin/python3 -B "$script_dir/verify_packaged_python.py" \
  --repo-root "$repo_root" \
  --app-bundle "$app_bundle" \
  --target "$target" \
  --expected-manifest-sha256 "$expected_manifest" \
  --native-smoke
codesign --verify --deep --strict --verbose=2 "$app_bundle"
printf 'Verified mounted DMG packaged Python: %s\n' "$dmg"
