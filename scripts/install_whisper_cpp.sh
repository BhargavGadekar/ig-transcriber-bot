#!/usr/bin/env bash
# Build whisper.cpp from source (CPU by default; CUDA and Metal optional).
#
# Usage:
#   scripts/install_whisper_cpp.sh [--dest DIR] [--version TAG] [--cuda] [--no-metal] [-j N]
#
# Defaults: --dest third_party/whisper.cpp  --version v1.9.5  jobs = nproc
# On macOS, Metal acceleration is enabled by default (Apple Silicon).
# Pass --cuda on Linux/NVIDIA to build with -DGGML_CUDA=ON (needs the CUDA toolkit).
set -euo pipefail

DEST="third_party/whisper.cpp"
VERSION="v1.9.5"
JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
CUDA=0
METAL=""  # empty = let cmake default decide (ON for macOS, OFF elsewhere)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --cuda) CUDA=1; shift ;;
    --no-metal) METAL=OFF; shift ;;
    -j|--jobs) JOBS="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

CMAKE_ARGS=(
  -DWHISPER_BUILD_TESTS=OFF
  -DWHISPER_BUILD_SERVER=OFF
  -DWHISPER_BUILD_EXAMPLES=ON
)
if [[ "$CUDA" == "1" ]]; then
  CMAKE_ARGS+=(-DGGML_CUDA=ON)
  echo ">> Building with CUDA support (requires CUDA toolkit)"
fi
if [[ -n "$METAL" ]]; then
  CMAKE_ARGS+=(-DGGML_METAL="$METAL")
fi

if [[ ! -d "$DEST" ]]; then
  echo ">> Cloning whisper.cpp @ $VERSION into $DEST"
  git clone --depth 1 --branch "$VERSION" https://github.com/ggml-org/whisper.cpp "$DEST"
else
  echo ">> Using existing checkout at $DEST (wanted: $VERSION)"
  git -C "$DEST" fetch --tags --depth 1 origin "$VERSION" 2>/dev/null || true
  git -C "$DEST" checkout --quiet "$VERSION" 2>/dev/null || \
    echo "!! Could not check out $VERSION; building what is there" >&2
fi

echo ">> Configuring: cmake ${CMAKE_ARGS[*]}"
cmake -S "$DEST" -B "$DEST/build" "${CMAKE_ARGS[@]}"

echo ">> Building (jobs=$JOBS)"
cmake --build "$DEST/build" --config Release -j "$JOBS"

BIN="$DEST/build/bin/whisper-cli"
if [[ ! -x "$BIN" ]]; then
  echo "!! Expected binary not found at $BIN" >&2
  exit 1
fi

echo ""
echo "whisper.cpp built successfully."
echo "  Binary : $BIN"
echo "Next steps:"
echo "  export WHISPER_BIN=\"$(cd "$(dirname "$BIN")" && pwd)/whisper-cli\""
echo "  scripts/download_model.sh large-v3-turbo-q5_0"
if [[ "$(uname)" == "Darwin" && -z "$METAL" ]]; then
  echo "Note: keep the binary in place — the Metal kernel (ggml-metal.metal) sits"
  echo "      next to it and is loaded at runtime. GPU acceleration is automatic."
fi
