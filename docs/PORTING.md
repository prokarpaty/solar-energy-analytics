# Porting checklist before the first usable release

1. Keep `/opt/solar-reports` unchanged. Create a clean Git clone at `/opt/solar-reports-dev`.
2. Copy only vetted source assets: `Dockerfile`, `requirements.txt`, `scripts/*.py`, `templates/*.html`, sanitized Compose. **Never copy `.env`, `secrets`, `reports`, `state`, `logs`, backups, live database or other private files.**
3. Review source files for embedded emails, IP addresses, tokens, personal names, location-specific labels, and private dashboard links. Use a secret scanner and manual code review before first push.
4. Make `config/sensors.yaml` configurable with robust validation. Support missing battery/phase metrics, multiple battery counts, correct unit conversions, and alternate inverter naming. Initial production config assumes a specific 76-sensor Deye installation and cannot be used as a generic profile.
5. Add translations to the reporting engine and templates; only the **wizard** is bilingual in this starter.
6. Replace hard-coded scheduler calendars with validated cron schedule parsing; preserve Kyiv/UTC DST behavior and SQLite deduplication.
7. Add Docker Compose and secure per-install volumes, so users can opt into SMTP and retain generated reports. Avoid placing secrets in image layers.
8. Add CI, unit tests and a completely clean-host install + restore test before publication as a functioning release.
9. Handle report retention, graceful shutdown, SMTP unknown outcomes, incomplete data and HA WebSocket connectivity.
10. Publish to GitHub only after a privacy review. Start with a private repository or review branch if possible.
