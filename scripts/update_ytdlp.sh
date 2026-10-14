#!/usr/bin/env bash
# Update yt-dlp inside the bot's virtualenv (Instagram extractors break often).
#
# Usage:
#   scripts/update_ytdlp.sh [VENV_DIR]          (default: ./venv)
#
# Optional restart of the service after update (so the new code is loaded):
#   RESTART_SERVICE=igtranscriber.service scripts/update_ytdlp.sh
#
# Cron example (daily 04:00, restart the systemd unit after updating):
#   0 4 * * * cd /opt/ig-transcriber && RESTART_SERVICE=igtranscriber.service \
#     scripts/update_ytdlp.sh venv >> data/logs/ytdlp_update.log 2>&1
set -euo pipefail

VENV="${1:-venv}"
PIP="$VENV/bin/pip"
if [[ ! -x "$PIP" ]]; then
  echo "!! pip not found at $PIP — pass the venv dir as the first argument" >&2
  exit 1
fi

echo ">> before: $("$VENV/bin/python" -c 'import yt_dlp; print(yt_dlp.version.__version__)' 2>/dev/null || echo 'not installed')"
"$PIP" install --upgrade yt-dlp
echo ">> after:  $("$VENV/bin/python" -c 'import yt_dlp; print(yt_dlp.version.__version__)')"

if [[ -n "${RESTART_SERVICE:-}" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    echo ">> restarting systemd unit $RESTART_SERVICE"
    sudo systemctl try-restart "$RESTART_SERVICE" || \
      echo "!! could not restart $RESTART_SERVICE (not running as root?)" >&2
  else
    echo "!! systemctl not available; restart the bot manually" >&2
  fi
fi
