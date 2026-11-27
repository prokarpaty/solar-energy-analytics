# Solar Energy Analytics

Self-hosted Home Assistant solar-energy reporting with an English/Ukrainian installation wizard, scheduled reports, interactive HTML, PDF and optional SMTP email. Designed for Deye inverters with configurable Home Assistant energy and measurement entities; availability of individual charts depends on mapped sensors and recorder statistics.

**Status:** release candidate on `develop`. Not yet a public v1.0.0 release. Keep the repository private until final release review.

## Requirements

- Linux (tested with Ubuntu 24.04.5 LTS)
- Docker Engine and Docker Compose v2
- Python 3.10+ for the wizard; PyYAML and `websocket-client` (the bootstrap can offer to install missing Ubuntu/Debian packages using apt and sudo)
- Home Assistant reachable from this machine, with a dedicated long-lived access token and historical recorder statistics
- Optional SMTP account supporting STARTTLS, e.g. Gmail with a Google App Password
- At least 3 GiB free disk space for installation preflight; report storage requires additional space

Docker installation itself is not automated. Run as a normal local user with Docker access (directly or via sudo); do not run the installer as root.

## Install / Встановлення

### 1. Prepare Ubuntu / Підготовка Ubuntu

On a clean Ubuntu 24.04 host, install the prerequisites for the installation wizard:

```bash
sudo apt update

sudo apt install -y \
  git \
  curl \
  ca-certificates \
  python3 \
  python3-yaml \
  python3-websocket

```

### Install Docker Engine and Compose / Встановлення Docker

On Ubuntu 24.04, install Docker Engine and the Compose v2 plugin:

```bash
sudo apt update

sudo apt install -y \
  docker.io \
  docker-compose-v2

sudo systemctl enable --now docker
```

Verify the installation:

```bash
sudo docker --version
sudo docker compose version
sudo docker info --format 'Docker Engine: {{.ServerVersion}}'
```

If `docker-compose-v2` is unavailable from your Ubuntu repositories, follow the [official Docker Engine and Compose installation guide](https://docs.docker.com/engine/install/ubuntu/) instead. Run the wizard as a normal user, not root; it can use `sudo` for Docker access.

### 2. Verify Home Assistant connectivity / Перевірка Home Assistant

Substitute **your own Home Assistant server IP address** in this example (the address below is a private-LAN example, not an automatic discovery setting):

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8123/api/
```

An HTTP `401` response is expected for an unauthenticated API request and confirms the server is reachable; HTTP `000` or a connection error means networking should be checked. On a separate host, do not use `127.0.0.1` unless Home Assistant is actually hosted there.

### 3. Clone and install / Клонування та встановлення

While this repository remains private, the machine must have a GitHub SSH key authorized to access it.

```bash
git clone git@github.com:prokarpaty/solar-energy-analytics.git

cd solar-energy-analytics

bash install.sh
```

Follow the English/Ukrainian wizard. It confirms configuration, offers to build the Docker image, and asks separately before starting the scheduler.

The bilingual wizard collects the Home Assistant URL and token; discovers sensor entities and helps map energy and optional measurements; configures installation/equipment/branding, timezone and report language; and offers daily, weekly, monthly, quarterly and yearly schedules plus optional SMTP delivery. SMTP authentication can be tested without sending a message. The installer validates configuration and **asks separately** before building the image and starting the scheduler. Do not enable automatic delivery if another installation is already sending the same reports.

### Report delivery times / Час надсилання звітів

For each enabled report type, the wizard asks for an optional **24-hour local send time**, e.g. `08:00` (default). The schedule uses the timezone selected in the wizard. Daily reports cover the previous day, weekly reports the previous Monday–Sunday week, and monthly/quarterly/yearly reports the previous completed calendar period. The earliest delivery time is the later of the requested clock time and the recorder-statistics delay (10 minutes by default); generation, API availability and SMTP retries can postpone actual delivery. The chosen time does not change the historical reporting period.

For an **existing installation**, do not rerun the installer: edit the private `config/schedule.yaml` file and add a per-report `send_time` value:

```yaml
reports:
  daily:
    enabled: true
    cron: "0 0 * * *"
    period: previous_day
    send_time: "08:00"
```

Retain all other entries in `config/schedule.yaml`. Back up the file first, then apply changes with `bash deploy.sh --stop` followed by `bash deploy.sh --start`. Previously queued reports retain their stored retry/dispatch times, so review scheduler status before changing an active schedule.

Private local files are ignored by Git: `.env`, `secrets/`, `config/sensors.yaml`, `config/schedule.yaml`, `config/installation.yaml`, `reports/`, `logs/`, `state/` and `backups/`. Never commit tokens, passwords, private reports or SQLite state. The wizard's dry run previews configuration; it does not deploy the application.

## Operations

```bash
bash deploy.sh --check
bash deploy.sh --build
bash deploy.sh --start
bash deploy.sh --status
bash deploy.sh --logs
bash deploy.sh --stop
```

The release container is non-root, read-only at the root filesystem, with dropped Linux capabilities and a 2 GiB memory limit. It uses host networking to access Home Assistant; assess the host firewall and network trust accordingly.

For manual report generation, first build the image and configure the installation:

```bash
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/generate_report.py --type daily

# Substitute the JSON filename generated above:
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/render_report.py /app/reports/daily/solar-daily-YYYY-MM-DD_YYYY-MM-DD.json --language uk
```

Generated bundles include a dataset JSON, interactive HTML, PDF and integrity manifest. To create an email preview rather than deliver it:

```bash
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/send_report.py /app/reports/daily/solar-daily-YYYY-MM-DD_YYYY-MM-DD.json --language uk --preview
```

## Backup, upgrade and rollback

```bash
bash deploy.sh --stop
bash maintenance.sh --backup
bash maintenance.sh --upgrade
# Inspect changes and restart manually only after validation:
bash deploy.sh --check
bash deploy.sh --start
```

`maintenance.sh --upgrade` expects a clean Git working tree and an upstream branch. It stops the scheduler and creates a backup before updating source and building the image. For rollback:

```bash
bash deploy.sh --stop
bash maintenance.sh --rollback
bash deploy.sh --check
```

Rollback restores the recorded Git revision and a locally tagged Docker image. It **does not** restore the archived private configuration or scheduler state automatically. A same-revision/image round-trip has been tested; real cross-version rollback and schema compatibility still require validation. The backup archives `.env`, `config/`, `secrets/` and `state/` but **not reports**: copy report archives separately for full disaster recovery. Keep private backups encrypted and off-host.

## CI and security

GitHub Actions validates shell/Python syntax and Compose configuration, builds the image, runs unit tests in a restricted Docker container and runs Trivy. Its security gate blocks **fixable** HIGH/CRITICAL findings; vulnerabilities without fixes are not blocking and need review. The action is pinned to a verified commit. Synthetic credentials are used in CI; nothing deploys to the home server.

## Limitations

- Historical reports depend on the availability, timestamps and completeness of Home Assistant recorder statistics. Missing historical periods are flagged rather than fabricated.
- Configured energy entities must provide compatible cumulative energy statistics. Optional equipment readings/charts vary by installation.
- SMTP acceptance is not an exactly-once guarantee. Delivery marked *unknown* should be reviewed before retrying.
- Source/configuration are bind-mounted; image-only rollback is insufficient.
- CI passing does not constitute a full security audit or a clean-room installation on another machine.
- v1.0.0 publication, cross-version upgrade/rollback validation and review of residual vulnerabilities remain release tasks.
