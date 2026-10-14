#!/usr/bin/env bash
# Download a Whisper ggml model and the Silero VAD model used with --vad.
#
# Usage:
#   scripts/download_model.sh [MODEL] [DIR]
#
# MODEL defaults to large-v3-turbo-q5_0. Others worth knowing:
#   tiny  base  small  medium  large-v3  large-v3-turbo  large-v3-turbo-q8_0
#   (quantized variants: tiny-q5_1 base-q5_1 small-q5_1 medium-q5_0 large-v3-q5_0 ...)
set -euo pipefail

MODEL="${1:-large-v3-turbo-q5_0}"
DIR="${2:-models}"
BASE="https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VAD_BASE="https://huggingface.co/ggml-org/whisper-vad/resolve/main"
VAD_MODEL="ggml-silero-v6.2.0.bin"

mkdir -p "$DIR"

fetch() {
  local url="$1" out="$2"
  if [[ -s "$out" ]]; then
    echo ">> exists: $out"
    return
  fi
  echo ">> downloading $url"
  curl -L --fail --retry 3 -C - -o "$out.part" "$url"
  mv "$out.part" "$out"
  echo ">> saved:   $out ($(du -h "$out" | cut -f1))"
}

fetch "$BASE/ggml-$MODEL.bin" "$DIR/ggml-$MODEL.bin"
fetch "$VAD_BASE/$VAD_MODEL" "$DIR/$VAD_MODEL"

cat <<EOF

Models ready in $DIR/
  WHISPER_MODEL_PATH="$DIR/ggml-$MODEL.bin"
  WHISPER_MODEL_NAME="$MODEL"
  WHISPER_VAD_MODEL="$DIR/$VAD_MODEL"
EOF
