#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

cd -- "$(dirname -- "$(readlink -f -- "$0")")"

if [[ $# -gt 0 ]]; then
    exec python3 installer/wizard.py "$@"
fi

if [[ "$(id -u)" -eq 0 ]]; then
    echo "[ERROR] Run as a regular user."
    exit 1
fi

if [[ -e .env || -L .env ]]; then
    echo "[ERROR] Existing installation detected."
    echo "Use deploy.sh to manage the installation."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    sudo -v
fi

bash installer/bootstrap.sh

python3 installer/preflight.py

python3 installer/wizard.py

bash deploy.sh --check

echo
echo "Configuration completed / Налаштування завершено"

read -r -p "Build Docker image? / Зібрати Docker-образ? [Y/n]: " answer

case "${answer:-y}" in
    y|Y|yes|YES|т|Т|так)
        bash deploy.sh --build
        ;;
    *)
        echo "Build skipped / Збірку пропущено"
        exit 0
        ;;
esac

read -r -p "Start scheduler? / Запустити планувальник? [y/N]: " answer

case "${answer:-n}" in
    y|Y|yes|YES|т|Т|так)
        bash deploy.sh --start
        ;;
    *)
        echo "Scheduler not started / Планувальник не запущено"
        ;;
esac

echo
echo "[PASS] Installation completed"
echo "Management / Керування: bash deploy.sh --help"
