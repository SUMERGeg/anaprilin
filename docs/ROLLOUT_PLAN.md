# Rollout Plan (Soft Launch)

## Day 0: migration + smoke checks

1. Run migrations:
   - `python -m alembic -c backend/alembic.ini upgrade head`
2. Import legacy data:
   - `python data-migration/import_subscribers.py`
   - `python data-migration/import_confirmations.py`
3. Verify last 30 days:
   - `python data-migration/verify_last_30_days.py`
4. Check backend health:
   - `GET /healthz`
   - `GET /readyz`

## Days 1-3 (user #1 only)

1. User #1 uses PWA daily.
2. Monitor:
   - sync queue errors
   - push delivery logs
   - fallback email (if enabled)
3. Daily backup SQLite (cron).

## Days 4-7

1. Keep only user #1.
2. Confirm:
   - no data loss after offline usage
   - nag stops after `confirmed/skipped`
   - scheduler steady (`/readyz` + logs)

## Day 8: user #2 onboarding

1. Add user #2 (device-login).
2. Repeat quick onboarding checklist:
   - schedule set
   - push permission granted
   - test reminder delivered
3. Continue monitoring both users for 3-7 days.

