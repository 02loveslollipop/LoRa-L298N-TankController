#!/bin/bash
set -euo pipefail

TARGET="streamer"
BUILD_TAGS="cpu"
OUTPUT_MSG="Built CPU-only streamer (libx264)"
OTHER_HINT="--hw-accel"

if [[ ${1-} == "--hw-accel" ]]; then
    BUILD_TAGS=""
    OUTPUT_MSG="Built hardware-accelerated streamer (rkmpp)"
    OTHER_HINT="(no flag)"
fi

if [[ "$(uname -m)" != "aarch64" ]]; then
    export GOARCH=arm64
    export GOOS=linux
fi

GOFLAGS=(-ldflags "-s -w")
if [[ -n "$BUILD_TAGS" ]]; then
    GOFLAGS=(-tags "$BUILD_TAGS" "${GOFLAGS[@]}")
fi

CGO_ENABLED=0 go build "${GOFLAGS[@]}" -o "$TARGET"

echo "$OUTPUT_MSG"
echo "Binary: $TARGET"
echo "To build the other variant, rerun with $OTHER_HINT."