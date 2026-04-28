# Backend

Foundation layer for:

- FastAPI app
- SQLModel models
- Alembic migrations
- APScheduler jobs
- Web Push integration

Run target (later stages):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Migrations

```bash
python -m alembic -c alembic.ini upgrade head
```

## Demo auth flow for local usage

1. `POST /api/v1/auth/device-login`
2. Use response values in headers:
- `X-User-Id`
- `X-Device-Id`

## Scheduler + Push

- APScheduler minute tick runs automatically on app startup.
- Primary reminders are dispatched when current local user slot matches schedule.
- NAG reminders are sent every 10 minutes while event status is `pending` (max 6).
- Push subscription is auto-disabled on HTTP `410 Gone`.

Required env vars for Web Push:

- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT` (example: `mailto:you@example.com`)

Optional push tuning:

- `PUSH_TTL_SECONDS` (default `3600`)
- `PUSH_MAX_RETRIES` (default `3`)
- `PUSH_BACKOFF_SECONDS` (default `1.0`)
- `PUSH_TIMEOUT_SECONDS` (default `10`)

## Email fallback (optional)

If push is not delivered (`push_sent=0`), backend can send email fallback for users with email enabled.

SMTP env vars:

- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS` (`1` or `0`)

User flags:

- `email`
- `notify_email_enabled=true`

## Ops scripts

- Readiness probe:
  - `python ops/check_readyz.py --url http://127.0.0.1:8000/readyz`
- SQLite backup:
  - `python ops/backup_sqlite.py --database-url sqlite:///./anaprilin.db --backup-dir ./backups`
