#!/bin/bash

# ======================================================
# CONFIG
# ======================================================

PROJECT_DIR="$HOME/browser-bridge"
VENV_DIR="$PROJECT_DIR/bridge-env"
LOG_DIR="$PROJECT_DIR/logs"
CHROME_PROFILE="$HOME/.chrome-ai-profile"

CHROME_PORT=9222
BRIDGE_PORT=8080

mkdir -p "$LOG_DIR"

# ======================================================
# ACTIVATE VENV
# ======================================================

source "$VENV_DIR/bin/activate"

# ======================================================
# START CHROME IF NOT RUNNING
# ======================================================

if ! lsof -i:$CHROME_PORT > /dev/null; then

    echo "[+] Starting AI Chrome..."

    google-chrome-stable \
        --remote-debugging-port=$CHROME_PORT \
        --user-data-dir="$CHROME_PROFILE" \
        --window-size=1920,1080 \
        --new-window \
        --disable-session-crashed-bubble \
        > "$LOG_DIR/chrome.log" 2>&1 &

    sleep 5

else

    echo "[+] Chrome already running"

fi

# ======================================================
# START BRIDGE IF NOT RUNNING
# ======================================================

if ! lsof -i:$BRIDGE_PORT > /dev/null; then

    echo "[+] Starting bridge server..."

    cd "$PROJECT_DIR"

    nohup python bridge.py \
        > "$LOG_DIR/bridge.log" 2>&1 &

    sleep 3

else

    echo "[+] Bridge already running"

fi

# ======================================================
# HEALTH CHECK
# ======================================================

if curl -s http://127.0.0.1:$BRIDGE_PORT/health > /dev/null; then

    echo ""
    echo "======================================"
    echo "AI BRIDGE READY"
    echo "======================================"
    echo ""
    echo "OPENAI_API_BASE=http://127.0.0.1:8080/v1"
    echo "MODEL=openai/browser-model"
    echo ""

else

    echo "[-] Bridge health check failed"

fi
