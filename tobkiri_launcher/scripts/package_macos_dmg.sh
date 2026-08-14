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
Usage: package_macos_dmg.sh --app-bundle PATH --target TARGET --output-dir PATH \
  [--signing-identity "Developer ID Application: ..." | --allow-ad-hoc-local | \
   --ci-e2e-cert-sha256 SHA256]
EOF
}

app_bundle=''
target=''
output_dir=''
signing_identity=''
allow_ad_hoc_local=0
ci_e2e_cert_sha256=''

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
    --signing-identity)
      (($# >= 2)) || { usage; exit 2; }
      ((allow_ad_hoc_local == 0)) || { usage; exit 2; }
      signing_identity=$2
      shift 2
      ;;
    --allow-ad-hoc-local)
      [[ -z "$signing_identity" && -z "$ci_e2e_cert_sha256" ]] || { usage; exit 2; }
      allow_ad_hoc_local=1
      shift
      ;;
    --ci-e2e-cert-sha256)
      (($# >= 2)) || { usage; exit 2; }
      [[ -z "$signing_identity" && "$allow_ad_hoc_local" -eq 0 ]] || { usage; exit 2; }
      ci_e2e_cert_sha256=$2
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
if [[ -n "$signing_identity" && "$signing_identity" != "Developer ID Application: "* ]]; then
  printf 'release macOS signing identity must be Developer ID Application, not ad-hoc\n' >&2
  exit 1
fi
if [[ -z "$signing_identity" && "$allow_ad_hoc_local" -ne 1 \
   && -z "$ci_e2e_cert_sha256" ]]; then
  printf 'a Developer ID identity or explicit non-publishable CI/E2E identity is required\n' >&2
  exit 1
fi
if [[ -n "$ci_e2e_cert_sha256" \
   && ! "$ci_e2e_cert_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'CI/E2E signing certificate identity must be a lowercase SHA-256\n' >&2
  exit 1
fi
command -v ditto >/dev/null 2>&1 || {
  printf 'ditto is required to stage the app bundle\n' >&2
  exit 1
}
command -v plutil >/dev/null 2>&1 || {
  printf 'plutil is required to read the app bundle version\n' >&2
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
version=$(plutil -extract CFBundleShortVersionString raw -o - \
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
if [[ -e "$dmg_path" || -L "$dmg_path" ]]; then
  printf 'Refusing to overwrite existing macOS installer: %s\n' "$dmg_path" >&2
  exit 1
fi

script_dir=$(cd "$(dirname "$0")" && pwd -P)
workspace_identity=$(/usr/bin/python3 -I -B \
  "$script_dir/cleanup_macos_dmg_workspace.py" create --parent "$output_dir")
IFS=$'\t' read -r work_dir work_device work_inode <<<"$workspace_identity"
[[ -n "$work_dir" && "$work_device" =~ ^[0-9]+$ && "$work_inode" =~ ^[0-9]+$ ]] || {
  printf 'DMG workspace helper returned an invalid ownership identity\n' >&2
  exit 1
}
staging_dir="$work_dir/staging"
image_dir="$work_dir/images"
mkdir "$staging_dir" "$image_dir"
owned_image_paths=()
cleanup() {
  local exit_status
  exit_status=$1

  trap - EXIT HUP INT QUIT TERM

  if [[ -n "${work_dir:-}" && ( -e "$work_dir" || -L "$work_dir" ) ]]; then
    local workspace_verified=0
    if /usr/bin/python3 -I -B \
      "$script_dir/cleanup_macos_dmg_workspace.py" verify \
      --parent "$output_dir" \
      --workspace "$work_dir" \
      --device "$work_device" \
      --inode "$work_inode"; then
      workspace_verified=1
    else
      printf 'Temporary DMG workspace identity changed; cleanup refused: %s\n' \
        "$work_dir" >&2
      if ((exit_status == 0)); then
        exit_status=1
      fi
    fi
    if ((workspace_verified == 1)) && ! detach_owned_images; then
      printf 'Could not detach every invocation-owned disk image during cleanup\n' >&2
      if ((exit_status == 0)); then
        exit_status=1
      fi
    fi
    if ((workspace_verified == 1)) && ! /usr/bin/python3 -I -B \
      "$script_dir/cleanup_macos_dmg_workspace.py" cleanup \
      --parent "$output_dir" \
      --workspace "$work_dir" \
      --device "$work_device" \
      --inode "$work_inode"; then
      printf 'Could not remove temporary DMG workspace: %s\n' "$work_dir" >&2
      if ((exit_status == 0)); then
        exit_status=1
      fi
    fi
  fi
  return "$exit_status"
}
trap 'cleanup $?' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 131' QUIT
trap 'exit 143' TERM

find_owned_device() {
  local target=$1
  local info=''

  if ! info=$(hdiutil info); then
    return 1
  fi

  awk -v target="$target" '
    function trim(value) {
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      return value
    }

    /^image-path[[:space:]]*:/ {
      path = $0
      sub(/^[^:]*:[[:space:]]*/, "", path)
      in_target = (trim(path) == target)
      next
    }

    in_target && $0 ~ /^\/dev\/disk[0-9]+([[:space:]]|$)/ {
      print $1
      exit
    }
  ' <<<"$info"
}

detach_owned_image() {
  local image_path=$1
  local device=''

  if ! device=$(find_owned_device "$image_path"); then
    printf 'Could not inspect hdiutil state while checking owned image: %s\n' \
      "$image_path" >&2
    return 1
  fi
  [[ -n "$device" ]] || return 0

  printf 'Detaching invocation-owned disk image: %s (%s)\n' "$image_path" "$device" >&2
  if ! hdiutil detach "$device"; then
    printf 'Could not detach invocation-owned disk image: %s (%s)\n' \
      "$image_path" "$device" >&2
    return 1
  fi
}

detach_owned_images() {
  local image_path=''
  local failed=0

  (( ${#owned_image_paths[@]} > 0 )) || return 0
  for image_path in "${owned_image_paths[@]}"; do
    if ! detach_owned_image "$image_path"; then
      failed=1
    fi
  done
  return "$failed"
}

replay_stderr() {
  local stderr_path=$1
  if [[ -s "$stderr_path" ]]; then
    cat "$stderr_path" >&2
  fi
}

is_transient_busy_failure() {
  local status=$1
  local stderr_path=$2

  # hdiutil's canonical diagnostic is "Resource busy"; EBUSY is status 16.
  if [[ "$status" -eq 16 ]]; then
    return 0
  fi
  [[ "$status" -eq 1 ]] || return 1
  grep -Eiq 'resource[[:space:]]+busy|(^|[^[:alnum:]_])ebusy([^[:alnum:]_]|$)' \
    "$stderr_path"
}

publish_verified_dmg() {
  local source_path=$1

  if [[ -e "$dmg_path" || -L "$dmg_path" ]]; then
    printf 'Refusing to overwrite existing macOS installer: %s\n' "$dmg_path" >&2
    return 1
  fi

  # A hard link creates the final name atomically and fails if another writer
  # wins the race.  It is safe here because both paths are in output_dir.
  if ! ln "$source_path" "$dmg_path"; then
    printf 'Could not publish macOS installer without overwriting output: %s\n' \
      "$dmg_path" >&2
    return 1
  fi
  if ! rm -f -- "$source_path"; then
    printf 'Published macOS installer but could not remove its temporary link: %s\n' \
      "$source_path" >&2
    return 1
  fi
}

printf 'Verifying signed app bundle: %s\n' "$app_bundle"
codesign --verify --deep --strict --verbose=2 "$app_bundle"
if [[ -n "$signing_identity" ]]; then
  signing_details="$(codesign --display --verbose=4 "$app_bundle" 2>&1)"
  if ! grep -Fqx "Authority=$signing_identity" <<<"$signing_details"; then
    printf 'macOS app is not signed by the requested Developer ID identity\n' >&2
    exit 1
  fi
elif [[ -n "$ci_e2e_cert_sha256" ]]; then
  bundle_identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
    "$app_bundle/Contents/Info.plist")
  [[ "$bundle_identifier" == 'dev.tobkiri.launcher.ci-e2e' ]] || {
    printf 'CI/E2E artifact has the wrong bundle identifier: %s\n' \
      "$bundle_identifier" >&2
    exit 1
  }
  marker="$app_bundle/Contents/Resources/NON_PUBLISHABLE_CI_E2E_ARTIFACT.txt"
  [[ -f "$marker" && ! -L "$marker" ]] || {
    printf 'CI/E2E artifact is missing its signed non-publishable marker\n' >&2
    exit 1
  }
  artifact_policy="$app_bundle/Contents/Resources/ci-e2e-artifact-policy.v1.json"
  expected_policy="$script_dir/../src-tauri/ci-e2e/ci-e2e-artifact-policy.v1.json"
  [[ -f "$artifact_policy" && ! -L "$artifact_policy" ]] \
    && cmp -s "$expected_policy" "$artifact_policy" || {
    printf 'CI/E2E artifact policy is missing or differs from its build domain\n' >&2
    exit 1
  }
  python3 -B "$script_dir/../../.github/scripts/macos_ci_artifact.py" verify \
    --app-bundle "$app_bundle" \
    --expected-certificate-sha256 "$ci_e2e_cert_sha256"
fi

printf 'Staging signed app bundle for DMG: %s\n' "$app_name"
ditto "$app_bundle" "$staging_dir/$app_name"
codesign --verify --deep --strict --verbose=2 "$staging_dir/$app_name"
ln -s /Applications "$staging_dir/Applications"

create_attempts=3
temporary_dmg_path=''
create_status=1
for ((attempt = 1; attempt <= create_attempts; attempt++)); do
  temporary_dmg_path="$image_dir/${app_stem}_${version}_${architecture_suffix}.attempt-${attempt}.dmg"
  owned_image_paths+=("$temporary_dmg_path")
  create_stderr="$work_dir/hdiutil-create-${attempt}.stderr"

  printf 'Creating read-only UDZO installer (attempt %d/%d): %s\n' \
    "$attempt" "$create_attempts" "$temporary_dmg_path"
  if hdiutil create \
    -srcfolder "$staging_dir" \
    -volname "$app_stem" \
    -fs APFS \
    -format UDZO \
    "$temporary_dmg_path" \
    2>"$create_stderr"; then
    replay_stderr "$create_stderr"
    create_status=0
    break
  else
    create_status=$?
    replay_stderr "$create_stderr"
  fi

  if ! is_transient_busy_failure "$create_status" "$create_stderr"; then
    printf 'hdiutil create failed with status %d; not retrying\n' "$create_status" >&2
    exit "$create_status"
  fi
  if ((attempt == create_attempts)); then
    printf 'hdiutil create exhausted %d attempts on a recognized busy failure\n' \
      "$create_attempts" >&2
    exit "$create_status"
  fi

  if ! detach_owned_image "$temporary_dmg_path"; then
    printf 'Refusing to retry hdiutil create without safely detaching its owned image\n' >&2
    exit "$create_status"
  fi
  if ! rm -f -- "$temporary_dmg_path"; then
    printf 'Could not remove failed temporary disk image: %s\n' \
      "$temporary_dmg_path" >&2
    exit 1
  fi
  printf 'Retrying hdiutil create after recognized busy failure\n' >&2
  sleep "$attempt"
done

if ((create_status != 0)); then
  printf 'hdiutil create did not produce a disk image\n' >&2
  exit 1
fi

printf 'Verifying disk image integrity: %s\n' "$temporary_dmg_path"
hdiutil verify "$temporary_dmg_path"
[[ -s "$temporary_dmg_path" ]] || {
  printf 'hdiutil created an empty disk image: %s\n' "$temporary_dmg_path" >&2
  exit 1
}

# hdiutil can leave a failed or verified image attached while diskimages-helper
# drains.  Before publication, prove that every candidate is detached.  The
# cleanup trap repeats the same exact-path-only check on all exit paths.
if ! detach_owned_images; then
  printf 'Refusing to publish a disk image that could not be safely detached\n' >&2
  exit 1
fi
publish_verified_dmg "$temporary_dmg_path"

printf 'Created verified macOS installer: %s\n' "$dmg_path"
