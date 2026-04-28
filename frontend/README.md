# Frontend (PWA)

Stack:

- React + TypeScript + Vite
- Dexie for IndexedDB
- Workbox for service worker/offline

Implemented:

- Screens: `Today`, `Calendar`, `Schedule Settings`, `Sync Status`
- IndexedDB tables: `local_schedule`, `local_events`, `outbox`, `sync_meta`
- Outbox sync on `online` and manual retry in Sync screen
- Workbox service worker (`injectManifest`) with:
  - precache app shell
  - runtime cache for API GET/static assets
  - offline navigation fallback
  - push + notification click deeplink handling

Run:

```bash
npm install
npm run dev
```

Build:

```bash
npm run typecheck
npm run build
```

Optional env:

- `VITE_API_BASE` (default: `/api/v1`)
- `VITE_VAPID_PUBLIC_KEY` (required for enabling push subscription)
