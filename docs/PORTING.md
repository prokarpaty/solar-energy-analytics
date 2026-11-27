# Release and migration validation

This document records the completed checks and the remaining follow-up work for the first public release of Solar Energy Analytics.

## Verified November 27, 2026

- The isolated Ubuntu 24.04 installation completed from a fresh repository clone and the bilingual wizard.
- Home Assistant authentication, automatic Deye mapping, daily report generation, interactive HTML, PDF and report manifest were verified.
- A real Gmail SMTP report was successfully delivered and confirmed received from the isolated VM.
- The production Home Assistant host migrated from /opt/solar-reports to /opt/solar-energy-analytics, while keeping the old deployment available for rollback.
- Production settings, secrets and a full report archive were retained. Six historical successful-delivery records were preserved; the scheduler database integrity check returned OK.
- The new production scheduler started successfully without errors. The former production container remained stopped.
- GitHub Actions passed for the develop branch and merged main commit.

## Known limitations and follow-up validation

- Verify the first automatically scheduled email on the migrated production deployment and check its attachments.
- A previous-version rollback and forward upgrade across changing configurations and database schemas have not been exercised as a full disaster-recovery drill.
- Backups created by maintenance.sh omit reports, and private configuration/state restoration is manual.
- Trivy CI currently blocks fixable HIGH/CRITICAL findings, not all unfixed vulnerabilities; review remaining findings before public publication.
- GitHub repository history must be assessed for secret/private-data exposure before switching visibility to public.
- The source currently supports a verified Deye naming profile; other inverters and naming conventions may require manual configuration or code changes.
- Delivery send_time is a minimum scheduled release time, not a guarantee of mailbox arrival.
- The new production installation currently retains its existing midnight-based schedule until separately reconfigured.

Do not publish credentials, personal installation data, local network information, archived reports or state databases. Keep credentials in the private, gitignored installation directories.
