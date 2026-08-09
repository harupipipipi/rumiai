#!/usr/bin/env bash
# Package a signed Tauri macOS app without Finder automation.
#
# Tauri's bundled create-dmg wrapper mounts an intermediate HFS+ image and
# invokes Finder through AppleScript.  That is unnecessary for CI packaging
# and has been observed to fail on the GitHub macOS Intel image after the app
# bundle has already been built and signed.  Keep the app signature intact and
# use hdiutil's direct read-only image path instead.

set -Eeuo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: package_macos_dmg.sh --app-bundle PATH --target TARGET --output-dir PATH
EOF
}

app_bundle=''
target=''
output_dir=''

while (($# > 0)); do
  case "$1" in
    --app-bundle)
      (($# >= 2)) || { usage; exit 2; }
      app_bundle=$2
      shift 2
      ;;
    --target)
      (($# >= 2)) || { usage; exit 2; }
      target=$2
      shift 2
      ;;
    --output-dir)
      (($# >= 2)) || { usage; exit 2; }
      output_dir=$2
      shift 2
      ;;
    -h|--help)
      usage >&1
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$app_bundle" || -z "$target" || -z "$output_dir" ]]; then
  usage
  exit 2
fi

case "$target" in
  x86_64-apple-darwin)
    architecture_suffix='x64'
    ;;
  aarch64-apple-darwin)
    architecture_suffix='aarch64'
    ;;
  *)
    printf 'Unsupported macOS target: %s\n' "$target" >&2
    exit 2
    ;;
esac

[[ -d "$app_bundle" ]] || {
  printf 'Tauri app bundle does not exist: %s\n' "$app_bundle" >&2
  exit 1
}
[[ -f "$app_bundle/Contents/Info.plist" ]] || {
  printf 'Tauri app bundle is missing Contents/Info.plist: %s\n' "$app_bundle" >&2
  exit 1
}

command -v codesign >/dev/null 2>&1 || {
  printf 'codesign is required to verify the signed app bundle\n' >&2
  exit 1
}
command -v ditto >/dev/null 2>&1 || {
  printf 'ditto is required to stage the app bundle\n' >&2
  exit 1
}
command -v hdiutil >/dev/null 2>&1 || {
  printf 'hdiutil is required to create the macOS installer\n' >&2
  exit 1
}

app_bundle=$(cd "$app_bundle" && pwd -P)
mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)

app_name=$(basename "$app_bundle")
[[ "$app_name" == *.app ]] || {
  printf 'Expected a .app bundle, got: %s\n' "$app_name" >&2
  exit 1
}
app_stem=${app_name%.app}
version=$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - \
  "$app_bundle/Contents/Info.plist")
[[ -n "$version" ]] || {
  printf 'Tauri app bundle has no CFBundleShortVersionString: %s\n' "$app_bundle" >&2
  exit 1
}
if [[ ! "$version" =~ ^[A-Za-z0-9][A-Za-z0-9.+_-]*$ ]]; then
  printf 'Tauri app bundle has an unsafe version for a DMG filename: %s\n' "$version" >&2
  exit 1
fi

dmg_path="$output_dir/${app_stem}_${version}_${architecture_suffix}.dmg"
staging_dir=$(mktemp -d "${TMPDIR:-/tmp}/tobkiri-dmg.XXXXXX")
cleanup() {
  if [[ -n "${staging_dir:-}" && -d "$staging_dir" ]]; then
    rm -rf "$staging_dir"
  fi
}
trap cleanup EXIT

printf 'Verifying signed app bundle: %s\n' "$app_bundle"
codesign --verify --deep --strict --verbose=2 "$app_bundle"

printf 'Staging signed app bundle for DMG: %s\n' "$app_name"
ditto "$app_bundle" "$staging_dir/$app_name"
codesign --verify --deep --strict --verbose=2 "$staging_dir/$app_name"
ln -s /Applications "$staging_dir/Applications"

printf 'Creating read-only UDZO installer: %s\n' "$dmg_path"
hdiutil create \
  -srcfolder "$staging_dir" \
  -volname "$app_stem" \
  -fs APFS \
  -format UDZO \
  -ov \
  "$dmg_path"

printf 'Verifying disk image integrity: %s\n' "$dmg_path"
hdiutil verify "$dmg_path"
[[ -s "$dmg_path" ]] || {
  printf 'hdiutil created an empty disk image: %s\n' "$dmg_path" >&2
  exit 1
}

printf 'Created verified macOS installer: %s\n' "$dmg_path"
