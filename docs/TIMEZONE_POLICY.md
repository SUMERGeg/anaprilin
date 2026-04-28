# Timezone Policy v1

## Canonical storage

- Store all event timestamps in UTC in DB.
- Store user timezone as IANA string in `users.timezone`.

## Default timezone

- Default user timezone: `Europe/Moscow`.

## API rules

- Server accepts:
  - UTC timestamps (`2026-04-28T10:15:00Z`)
  - or local datetime + timezone context (for selected endpoints)
- Server normalizes and persists in UTC.

## Scheduling rules

- Reminder schedule is user-local wall clock time (for example `09:00`, `15:00`, `21:00`).
- Scheduler computes next run in user timezone, then converts runtime to UTC.

## Client rules

- PWA renders day/calendar in user timezone.
- Offline events are timestamped with device time and timezone metadata, then normalized on sync.

