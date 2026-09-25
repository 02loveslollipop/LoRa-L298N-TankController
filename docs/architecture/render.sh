#!/usr/bin/env bash
set -euo pipefail

architecture_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 python3 "$architecture_dir/system-architecture.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$architecture_dir/aws-deployment.py"

if command -v magick >/dev/null 2>&1; then
  rasterizer=(magick)
elif command -v convert >/dev/null 2>&1; then
  rasterizer=(convert)
else
  echo "ImageMagick (magick or convert) is required for PNG rendering." >&2
  exit 1
fi

for name in system-architecture aws-deployment; do
  "${rasterizer[@]}" -background white \
    "$architecture_dir/rendered/$name.svg" -depth 8 \
    "$architecture_dir/rendered/$name.png"
done

echo "Rendered 2880×1620 SVG and PNG diagrams in $architecture_dir/rendered/"
