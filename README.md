# Solar Energy Analytics — bilingual installation wizard starter

**Development scaffold, not a runnable reporting release.** This package is designed to safely collect configuration before the production reporting engine is reviewed and ported. It neither builds nor starts Docker containers and sends no email.

## Intended installation

```bash
git clone https://github.com/prokarpaty/solar-energy-analytics.git
cd solar-energy-analytics
bash install.sh
```

**The GitHub repository must be created and this starter published before these commands work.**

The first prompt is a choice of **English / Українська**. The wizard then requests Home Assistant connection details and token, timezone, report language, inverter type, enabled report periods, optional SMTP credentials, and explains the required sensor mapping. All credentials and user-specific sensor/schedule settings are saved to ignored, private files (`.env`, `secrets/`, `config/sensors.yaml`, `config/schedule.yaml`) and are not committed to Git.

To test the prompts safely:

```bash
bash install.sh --dry-run
```

To validate the presence of local setup files:

```bash
bash install.sh --check
```

Python 3.10+ is required for the wizard; Docker is required only once the reporting runtime is added.

## Environments

- **Production:** `/opt/solar-reports` — existing running deployment, never changed by these scripts.
- **Development:** `/opt/solar-reports-dev` — clone repository here and develop/test separately. The starter does not manage production.

## Important next work

Port and audit the existing production `scripts/`, `templates/`, `Dockerfile`, dependencies and Compose model **from sanitized sources**. Do not upload the production tarball, live `.env`, private tokens, reports, logs or SQLite data. Implement actual sensor onboarding and optional fields before claiming general compatibility. See [porting checklist](docs/PORTING.md).
