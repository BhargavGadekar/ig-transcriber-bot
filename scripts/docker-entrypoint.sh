#!/bin/sh
# Docker entrypoint: make sure model files exist, then start the bot.
set -e

MODELS_DIR="${MODELS_DIR:-/app/models}"
mkdir -p "$MODELS_DIR" /app/data

MODEL_PATH="${WHISPER_MODEL_PATH:-$MODELS_DIR/ggml-large-v3-turbo-q5_0.bin}"
VAD_PATH="${WHISPER_VAD_MODEL:-$MODELS_DIR/ggml-silero-v6.2.0.bin}"

fetch() {
  url="$1"; out="$2"
  if [ -s "$out" ]; then
    echo ">> model exists: $out"
    return
  fi
  echo ">> downloading $url"
  curl -L --fail --retry 3 -C - -o "$out.part" "$url"
  mv "$out.part" "$out"
}

case "$MODEL_PATH" in
  /*) ;;
  *) MODEL_PATH="$MODELS_DIR/$(basename "$MODEL_PATH")" ;;
esac
case "$VAD_PATH" in
  /*) ;;
  *) VAD_PATH="$MODELS_DIR/$(basename "$VAD_PATH")" ;;
esac

fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$(basename "$MODEL_PATH")" "$MODEL_PATH"
fetch "https://huggingface.co/ggml-org/whisper-vad/resolve/main/$(basename "$VAD_PATH")" "$VAD_PATH"

export WHISPER_MODEL_PATH="$MODEL_PATH" WHISPER_VAD_MODEL="$VAD_PATH"
exec python3 main.py
