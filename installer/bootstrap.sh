#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
    echo "[ERROR] Run as a regular user."
    exit 1
fi

if [[ "$(uname -s)" != Linux ]]; then
    echo "[ERROR] Linux is required."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1 ||
   ! docker compose version >/dev/null 2>&1; then
    echo "[ERROR] Docker Engine and Compose v2 are required."
    echo "https://docs.docker.com/engine/install/"
    exit 1
fi

if command -v python3 >/dev/null 2>&1 &&
   python3 -c 'import sys, yaml, websocket; assert sys.version_info >= (3,10)' \
       >/dev/null 2>&1; then
    echo "[PASS] Python dependencies available"
    exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
    echo "[ERROR] Install Python >= 3.10, PyYAML and websocket-client."
    exit 1
fi

echo "Required packages:"
echo "  python3 python3-yaml python3-websocket"

read -r -p "Install dependencies? / Встановити залежності? [Y/n]: " answer

case "${answer:-y}" in
    y|Y|yes|YES|т|Т|так)
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends \
            python3 python3-yaml python3-websocket
        ;;
    *)
        exit 1
        ;;
esac

python3 -c 'import sys, yaml, websocket; assert sys.version_info >= (3,10)'

echo "[PASS] Python dependencies installed"
