#!/bin/bash

# Get directory where script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

# Paths
VENV_DIR="$DIR/../.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
LOG_DIR="$DIR/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

# Log files
MAIN_LOG="$LOG_DIR/pocketdev.log"
LT_LOG="$LOG_DIR/localtunnel.log"
PID_FILE="$LOG_DIR/.services.pid"

# Function to stop running services
stop_existing() {
  if [ -f "$PID_FILE" ]; then
    echo "Stopping existing background services..."
    while read -r pid; do
      if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
        echo "Killing process $pid..."
        kill "$pid" 2>/dev/null
        sleep 0.5
        kill -9 "$pid" 2>/dev/null
      fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi

  # Also clean up any stale processes on port 8002
  PORT_PID=$(lsof -t -i:8002)
  if [ -n "$PORT_PID" ]; then
    echo "Found process $PORT_PID running on port 8002. Killing it..."
    kill -9 $PORT_PID 2>/dev/null
  fi
}

# Run stop first to ensure clean state
stop_existing

echo "Starting PocketDev AI server in the background..."
if [ -f "$VENV_PYTHON" ]; then
  nohup "$VENV_PYTHON" app/main.py > "$MAIN_LOG" 2>&1 &
  API_PID=$!
  echo $API_PID > "$PID_FILE"
  echo "PocketDev AI API started with PID $API_PID. Logs at logs/pocketdev.log"
else
  echo "Error: Virtual environment python not found at $VENV_PYTHON"
  exit 1
fi

echo "Starting localtunnel in the background..."
# Run localtunnel
nohup npx localtunnel --port 8002 > "$LT_LOG" 2>&1 &
LT_PID=$!
echo $LT_PID >> "$PID_FILE"
echo "Localtunnel started with PID $LT_PID. Logs at logs/localtunnel.log"

# Wait a few seconds for localtunnel to retrieve the URL
echo "Waiting for localtunnel URL..."
for i in {1..10}; do
  sleep 1
  if grep -q "your url is:" "$LT_LOG"; then
    echo ""
    grep "your url is:" "$LT_LOG"
    echo ""
    break
  fi
done

echo "Services started successfully!"
echo "To view API logs: tail -f logs/pocketdev.log"
echo "To view Localtunnel logs: tail -f logs/localtunnel.log"
echo "To stop services, run: ./stop_services.sh"
