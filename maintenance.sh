#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

cd "$(dirname "$(realpath "$0")")"

ROOT="$PWD"
IMAGE="solar-energy-analytics:local"

if [[ "$(id -u)" -eq 0 ]]; then
    echo "[ERROR] Run as a regular user."
    exit 1
fi

if [[ ! -f .env || ! -f config/installation.yaml ]]; then
    echo "[ERROR] Installation not configured."
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
        -f compose.release.yaml \
        -p solar-energy-analytics "$@"
}

require_clean_git() {
    if [[ -n "$(git status --porcelain)" ]]; then
        echo "[ERROR] Git working tree is not clean."
        exit 1
    fi
}

backup() {
    require_clean_git

    if [[ -n "$(compose ps --status running -q)" ]]; then
        echo "[ERROR] Stop the release scheduler before backup."
        exit 1
    fi

    local stamp destination revision
    stamp="$(date -u +%Y%m%d_%H%M%S)"
    destination="$ROOT/backups/maintenance-$stamp"
    revision="$(git rev-parse HEAD)"

    mkdir -p backups
    chmod 700 backups
    mkdir -m 700 "$destination"

    printf '%s\n' "$revision" > "$destination/revision"

    "${DOCKER[@]}" image tag \
        "$IMAGE" "solar-energy-analytics:rollback-$stamp"

    printf '%s\n' \
        "solar-energy-analytics:rollback-$stamp" \
        > "$destination/image"

    tar -czf "$destination/private-config.tar.gz" \
        .env config secrets state

    (
        cd "$destination"
        sha256sum revision image private-config.tar.gz > SHA256SUMS
        sha256sum -c SHA256SUMS
    )

    printf '%s\n' "$destination" > backups/latest-maintenance.path

    echo "[PASS] Backup: $destination"
}

case "${1:---help}" in
    --backup)
        backup
        ;;

    --upgrade)
        require_clean_git

        git fetch origin

        compose stop
        backup

        git merge --ff-only '@{upstream}'

        bash deploy.sh --build
        bash deploy.sh --check

        echo "[PASS] Upgrade completed."
        echo "Review configuration before starting."
        echo "bash deploy.sh --start"
        ;;

    --rollback)
        require_clean_git

        destination="$(cat backups/latest-maintenance.path)"

        (
            cd "$destination"
            sha256sum -c SHA256SUMS
        )

        revision="$(cat "$destination/revision")"
        rollback_image="$(cat "$destination/image")"

        "${DOCKER[@]}" image inspect "$rollback_image" >/dev/null

        compose stop

        git switch --detach "$revision"

        "${DOCKER[@]}" image tag "$rollback_image" "$IMAGE"

        echo "[PASS] Source and image restored."
        echo "Private configuration and scheduler state preserved."
        echo "Configuration backup: $destination/private-config.tar.gz"
        echo "Review configuration before starting."
        ;;

    --help)
        echo "Solar Energy Analytics maintenance"
        echo "  --backup     Back up configuration, state and revision"
        echo "  --upgrade    Back up and upgrade"
        echo "  --rollback   Restore previous source and image"
        ;;

    *)
        echo "[ERROR] Unknown command"
        exit 2
        ;;
esac
