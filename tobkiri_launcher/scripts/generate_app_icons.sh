#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ICON="${ROOT_DIR}/assets/app-icon/tobkiri-launcher-icon.png"
ICONS_DIR="${ROOT_DIR}/src-tauri/icons"

if ! command -v magick >/dev/null 2>&1; then
  echo "ImageMagick 'magick' is required to generate app icons." >&2
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "macOS 'iconutil' is required to generate icon.icns." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_ICON}" ]]; then
  echo "Source icon not found: ${SOURCE_ICON}" >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

cropped_icon="${tmp_dir}/icon-cropped.png"
square_icon="${tmp_dir}/icon-square.png"
rounded_mask="${tmp_dir}/rounded-mask.png"
iconset_dir="${tmp_dir}/icon.iconset"

mkdir -p "${ICONS_DIR}" "${iconset_dir}"

bbox="$(
  magick "${SOURCE_ICON}" -alpha extract -threshold 0 -define connected-components:verbose=true -connected-components 8 null: 2>&1 \
    | awk '$1 != "0:" && $1 ~ /^[0-9]+:$/ { if (($4 + 0) > best_area) { best_area = $4 + 0; best_bbox = $2 } } END { print best_bbox }'
)"

if [[ -z "${bbox}" ]]; then
  # The Tobkiri source icon has an opaque background. It is intentionally a
  # complete square composition, so retain the whole canvas rather than
  # treating the absent alpha channel as an empty image.
  source_width="$(magick identify -format '%w' "${SOURCE_ICON}")"
  source_height="$(magick identify -format '%h' "${SOURCE_ICON}")"
  bbox="${source_width}x${source_height}+0+0"
fi

dimensions="${bbox%%+*}"
width="${dimensions%x*}"
height="${dimensions#*x}"
canvas_size=$(( (width > height ? width : height) * 115 / 100 ))

magick "${SOURCE_ICON}" -crop "${bbox}" +repage "${cropped_icon}"

# The source art is an opaque square. Preserve the white rounded launcher
# panel and its black illustration, while making only the outside corners
# transparent for macOS, Windows, and Linux icon surfaces.
corner_radius=$(( width * 20 / 100 ))
magick -size "${width}x${height}" xc:none -fill white \
  -draw "roundrectangle 0,0 $((width - 1)),$((height - 1)) ${corner_radius},${corner_radius}" \
  "${rounded_mask}"

# Tauri app icons should be square, so keep the visible art centered with a small transparent margin.
magick "${cropped_icon}" "${rounded_mask}" -alpha off -compose CopyOpacity -composite \
  -compose Over -background none -gravity center -extent "${canvas_size}x${canvas_size}" "${square_icon}"

magick "${square_icon}" -resize 32x32 "${ICONS_DIR}/32x32.png"
magick "${square_icon}" -resize 128x128 "${ICONS_DIR}/128x128.png"
magick "${square_icon}" -resize 256x256 "${ICONS_DIR}/128x128@2x.png"
magick "${square_icon}" -resize 512x512 "${ICONS_DIR}/icon.png"
magick "${square_icon}" -define icon:auto-resize=16,24,32,48,64,128,256 "${ICONS_DIR}/icon.ico"

for size in 16 32 128 256 512; do
  magick "${square_icon}" -resize "${size}x${size}" "${iconset_dir}/icon_${size}x${size}.png"
  magick "${square_icon}" -resize "$((size * 2))x$((size * 2))" "${iconset_dir}/icon_${size}x${size}@2x.png"
done

iconutil -c icns "${iconset_dir}" -o "${ICONS_DIR}/icon.icns"
