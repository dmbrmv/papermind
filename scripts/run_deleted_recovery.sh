#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <start|stop|status|restart> <kb_path>"
  exit 1
fi

ACTION="$1"
KB_PATH="$2"
VENV_BIN="/home/dmbrmv/Development/papermind/.venv/bin"
PAPERMIND_BIN="$VENV_BIN/papermind"
RECOVERY_DIR="$KB_PATH/.papermind/recovery"
PID_FILE="$RECOVERY_DIR/deleted_papers_recovery.pid"
LOG_FILE="$RECOVERY_DIR/deleted_papers_recovery.log"

mkdir -p "$RECOVERY_DIR"

start_runner() {
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
      echo "Recovery already running: $PID"
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  setsid "$PAPERMIND_BIN" --kb "$KB_PATH" audit recover-deleted >>"$LOG_FILE" 2>&1 < /dev/null &
  PID=$!
  echo "$PID" >"$PID_FILE"
  echo "Started recovery: $PID"
}

stop_runner() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "Recovery is not running"
    return 0
  fi

  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped recovery: $PID"
  else
    echo "Recovery pid file existed but process was not running"
  fi
  rm -f "$PID_FILE"
  return 0
}

status_runner() {
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
      echo "Recovery running: $PID"
    else
      echo "Recovery pid file exists but process is not running"
    fi
  else
    echo "Recovery not running"
  fi

  "$PAPERMIND_BIN" --kb "$KB_PATH" audit recover-status
}

case "$ACTION" in
  start)
    start_runner
    ;;
  stop)
    stop_runner
    ;;
  restart)
    stop_runner || true
    start_runner
    ;;
  status)
    status_runner
    ;;
  *)
    echo "Unknown action: $ACTION"
    exit 1
    ;;
esac
