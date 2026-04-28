# Stabilization Checklist

## Logs

1. Set `LOG_LEVEL=INFO` (or `DEBUG` for incident windows).
2. Keep process logs in systemd journal (or file rotation if needed).
3. Verify scheduler logs every day:
   - primary reminders
   - nag reminders
   - escalation reminders

## Alerts

1. Add cron for readiness probe:
   - `python backend/ops/check_readyz.py --url http://127.0.0.1:8000/readyz`
2. Optional webhook:
   - `--webhook-url https://...`

## Healthchecks

1. `GET /livez` -> process alive
2. `GET /readyz` -> DB reachable + scheduler running
3. `GET /healthz` -> basic API health

## Backup SQLite

1. Daily backup command:
   - `python backend/ops/backup_sqlite.py --database-url sqlite:///./backend/anaprilin.db --backup-dir ./backend/backups`
2. Verify restore test at least once per week.

## Email fallback (optional reserve channel)

Enable only if push permission is missing or unreliable:

1. Set SMTP env vars:
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `SMTP_FROM_EMAIL`
2. For a user, set:
   - `email`
   - `notify_email_enabled=true`
3. Behavior:
   - if push sent count is `0`, backend attempts email fallback.

## Definition of Done (DoD)

1. Offline intake mark works in PWA.
2. Outbox sync restores all offline actions without loss.
3. Push delivery meets SLA target.
4. Nag stops correctly after `confirmed/skipped`.
5. Last 30 days migration verified with `verify_last_30_days.py`.
6. Daily backup + readiness checks are active.

