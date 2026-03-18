#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run.sh 5001
#   PORT=5001 ./run.sh
#
# This script:
# - creates/uses .venv
# - installs requirements.txt
# - starts Flask server on 0.0.0.0:${PORT} in background via nohup
# - writes logs to logs/server.log and pid to logs/server.pid

PORT="${1:-${PORT:-5000}}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "PORT must be a number, got: $PORT" >&2
  exit 1
fi

mkdir -p logs

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ -f "logs/server.pid" ]; then
  OLD_PID="$(cat logs/server.pid || true)"
  if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "Server already running (pid=${OLD_PID}). Stop it first: ./stop.sh" >&2
    exit 1
  fi
fi

echo "Starting server on 0.0.0.0:${PORT} ..."
nohup python -c "from server import app; app.run(host='0.0.0.0', port=${PORT}, debug=False, threaded=True)" \
  > logs/server.log 2>&1 &

echo $! > logs/server.pid
sleep 0.3

echo "OK. pid=$(cat logs/server.pid)"
echo "Logs: logs/server.log"
echo "Open: http://<server-ip>:${PORT}/teacher"

