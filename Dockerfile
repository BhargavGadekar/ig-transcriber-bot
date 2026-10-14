# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Multi-stage image:
#   whisper-build : compiles whisper-cli (v1.9.5) from source
#   wheels        : pre-builds Python wheels (incl. tgcrypto-pyrofork C ext)
#   runtime       : python:3.11-slim + ffmpeg, whisper-cli, app code
# Model weights are NOT baked in — the entrypoint downloads them into the
# mounted /app/models volume on first start.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS whisper-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG WHISPER_VERSION=v1.9.5
# Extra cmake defines, e.g. -DGGML_CUDA=ON for NVIDIA GPU builds (requires the
# NVIDIA Container Toolkit at runtime and the CUDA toolkit in the builder —
# add build-essential's gcc plus cuda toolkit packages to the build stage):
#   docker build --build-arg WHISPER_CMAKE_EXTRA="-DGGML_CUDA=ON" .
ARG WHISPER_CMAKE_EXTRA=""
WORKDIR /src
RUN git clone --depth 1 --branch "${WHISPER_VERSION}" https://github.com/ggml-org/whisper.cpp . \
    && cmake -B build \
        -DWHISPER_BUILD_TESTS=OFF \
        -DWHISPER_BUILD_SERVER=OFF \
        -DWHISPER_BUILD_EXAMPLES=ON \
        -DGGML_METAL=OFF \
        ${WHISPER_CMAKE_EXTRA} \
    && cmake --build build --config Release -j"$(nproc)"

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS wheels

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=wheels /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --find-links=/wheels -r requirements.txt && rm -rf /wheels

COPY --from=whisper-build /src/build/bin/whisper-cli /opt/whisper-cli/whisper-cli

COPY . .
RUN chmod +x scripts/*.sh

ENV PYTHONUNBUFFERED=1 \
    WHISPER_BIN=/opt/whisper-cli/whisper-cli \
    WHISPER_MODEL_PATH=/app/models/ggml-large-v3-turbo-q5_0.bin \
    WHISPER_VAD_MODEL=/app/models/ggml-silero-v6.2.0.bin \
    DATA_DIR=/app/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
