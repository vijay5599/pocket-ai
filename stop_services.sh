#!/bin/bash

# Get directory where script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
LOG_DIR="$DIR/logs"
PID_FILE="$LOG_DIR/.services.pid"

if [ -f "$PID_FILE" ]; then
  echo "Stopping background services..."
  while read -r pid; do
    if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
      echo "Killing process $pid..."
      kill "$pid" 2>/dev/null
      sleep 0.5
      kill -9 "$pid" 2>/dev/null
    else
      echo "Process $pid already stopped."
    fi
  done < "$PID_FILE"
  rm -f "$PID_FILE"
  echo "Services stopped."
else
  echo "No service PID file found at $PID_FILE"
  # Let's also check if there's anything on port 8002
  PORT_PID=$(lsof -t -i:8002)
  if [ -n "$PORT_PID" ]; then
    echo "Found process $PORT_PID running on port 8002. Killing it..."
    kill -9 $PORT_PID 2>/dev/null
    echo "Process killed."
  else
    echo "No process running on port 8002."
  fi
fi
