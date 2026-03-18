#!/usr/bin/env bash
set -euo pipefail

if [ ! -f "logs/server.pid" ]; then
  echo "No logs/server.pid found. Nothing to stop."
  exit 0
fi

PID="$(cat logs/server.pid || true)"
if [ -z "${PID}" ]; then
  echo "Empty pid file. Removing it."
  rm -f logs/server.pid
  exit 0
fi

if kill -0 "${PID}" 2>/dev/null; then
  echo "Stopping pid=${PID} ..."
  kill "${PID}" || true
  sleep 0.4
  if kill -0 "${PID}" 2>/dev/null; then
    echo "Force killing pid=${PID} ..."
    kill -9 "${PID}" || true
  fi
else
  echo "Process pid=${PID} not running."
fi

rm -f logs/server.pid
echo "Stopped."

