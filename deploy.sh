#!/usr/bin/env bash
set -euo pipefail
umask 077

cd "$(dirname "$(realpath "$0")")"

PROJECT="solar-energy-analytics"
COMPOSE_FILE="compose.release.yaml"

if [[ "$(id -u)" -eq 0 ]]; then
    echo "[ERROR] Run as a regular user."
    exit 1
fi

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
else
    sudo -v
    DOCKER=(sudo docker)
fi

compose() {
    "${DOCKER[@]}" compose \
        -f "$COMPOSE_FILE" \
        -p "$PROJECT" "$@"
}

check_config() {
    for file in \
        .env \
        config/sensors.yaml \
        config/schedule.yaml \
        config/installation.yaml \
        secrets/ha_token
    do
        if [[ ! -f "$file" || -L "$file" ]]; then
            echo "[ERROR] Missing or unsafe file: $file"
            exit 1
        fi
    done

    python3 installer/preflight.py
    compose config --quiet

    echo "[PASS] Deployment configuration"
}

case "${1:---check}" in
    --check)
        check_config
        ;;

    --build)
        check_config
        compose build
        ;;

    --start)
        if [[ -f docker-compose.yml || -f docker-compose.yaml || -f compose.yaml || -f compose.yml ]]; then
            echo "[ERROR] Existing Compose configuration detected."
            echo "Use a separate release installation directory."
            exit 1
        fi

        check_config
        compose up -d --no-build
        compose ps
        ;;

    --stop)
        compose stop
        ;;

    --restart)
        compose restart
        ;;

    --status)
        compose ps
        ;;

    --logs)
        compose logs --tail 100
        ;;

    --help)
        echo "Solar Energy Analytics deployment"
        echo
        echo "  --check    Validate configuration"
        echo "  --build    Build Docker image"
        echo "  --start    Start application"
        echo "  --stop     Stop application"
        echo "  --restart  Restart application"
        echo "  --status   Show container status"
        echo "  --logs     Show recent logs"
        ;;

    *)
        echo "[ERROR] Unknown command"
        exit 2
        ;;
esac
