# Anaprilin iOS PWA Migration

This repository contains migration work from Telegram bot reminders to an offline-first iPhone PWA with a Python backend.

## Monorepo structure

- `backend/` - API, core domain logic, scheduler, and DB models
- `frontend/` - PWA client
- `data-migration/` - scripts for importing legacy JSON data
- `docs/` - contracts and architecture decisions

## Foundation decisions

- API contract v1: `docs/API_CONTRACT_V1.md`
- Status model: `docs/STATUS_MODEL.md`
- Timezone policy: `docs/TIMEZONE_POLICY.md`
- Rollout plan: `docs/ROLLOUT_PLAN.md`
- Stabilization checklist: `docs/STABILIZATION_CHECKLIST.md`

## Docker (foundation)

```bash
docker compose up --build -d
```
