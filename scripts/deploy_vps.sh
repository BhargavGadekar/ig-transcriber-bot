#!/usr/bin/env bash
# ==============================================================================
# ig-transcriber-bot: Universal 1-Click VPS Deployment & Optimization Script
# Optimized specifically for resource-constrained environments (e.g. 2GB RAM, 4-core VPS)
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  Setting up ig-transcriber-bot on Linux VPS"
echo "=========================================================="

# 1. Root / Sudo Check
if [[ "$EUID" -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 2. Check System RAM & Auto-Configure Swapfile
if [[ -f /proc/meminfo ]]; then
  TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  TOTAL_RAM_MB=$((TOTAL_RAM_KB / 1024))
  SWAP_TOTAL_KB=$(grep SwapTotal /proc/meminfo | awk '{print $2}')

  echo ">> Detected RAM: ${TOTAL_RAM_MB} MB"

  if [[ "$SWAP_TOTAL_KB" -lt 1048576 && "$TOTAL_RAM_MB" -le 2500 ]]; then
    echo ">> Low RAM detected (<= 2.5 GB) with little/no swap. Creating 2GB swapfile..."
    if [[ ! -f /swapfile ]]; then
      $SUDO fallocate -l 2G /swapfile || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048
      $SUDO chmod 600 /swapfile
      $SUDO mkswap /swapfile
      $SUDO swapon /swapfile
      if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab
      fi
      $SUDO sysctl vm.swappiness=10
      echo "vm.swappiness=10" | $SUDO tee -a /etc/sysctl.d/99-swappiness.conf >/dev/null || true
      echo ">> 2GB Swapfile successfully configured and active."
    else
      echo ">> /swapfile already exists."
      $SUDO swapon /swapfile 2>/dev/null || true
    fi
  fi
fi

# 3. Install System Packages
echo ">> Installing required packages (ffmpeg, cmake, build-essential, python3)..."
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -y
  $SUDO apt-get install -y --no-install-recommends \
    ffmpeg curl git cmake build-essential python3 python3-venv python3-pip ca-certificates
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y ffmpeg cmake gcc-c++ git python3 python3-pip make
elif command -v yum >/dev/null 2>&1; then
  $SUDO yum install -y epel-release || true
  $SUDO yum install -y ffmpeg cmake gcc-c++ git python3 python3-pip make
fi

# 4. Compile whisper.cpp natively for this CPU
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BOT_DIR"

echo ">> Compiling whisper.cpp natively for host CPU architecture..."
bash scripts/install_whisper_cpp.sh

# 5. Download Default Optimized Model (large-v3-turbo-q5_0 & VAD)
echo ">> Verifying model files..."
bash scripts/download_model.sh large-v3-turbo-q5_0

# 6. Set up Python Virtual Environment
echo ">> Setting up Python virtual environment..."
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 7. Check .env configuration
if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    echo ">> Created .env from .env.example. Please edit .env with your TG_BOT_TOKEN and credentials!"
  fi
fi

# 8. Create optional systemd service
SERVICE_FILE="/etc/systemd/system/ig-transcriber-bot.service"
if [[ -d "/etc/systemd/system" ]]; then
  echo ">> Generating systemd service at $SERVICE_FILE..."
  cat <<EOF | $SUDO tee "$SERVICE_FILE" >/dev/null
[Unit]
Description=Instagram Transcriber Telegram Bot
After=network.target

[Service]
Type=simple
User=${USER:-root}
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python main.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
MemoryMax=1850M

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  echo ">> Systemd service created! To start and enable on boot:"
  echo "   sudo systemctl enable --now ig-transcriber-bot"
  echo "   sudo systemctl status ig-transcriber-bot"
fi

echo ""
echo "=========================================================="
echo "  VPS Deployment & Optimization Complete!"
echo "  Run manually with: ./venv/bin/python main.py"
echo "  Or via systemd:    sudo systemctl start ig-transcriber-bot"
echo "=========================================================="
