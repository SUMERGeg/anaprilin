# API Contract v1 (Foundation Draft)

## Base

- Base path: `/api/v1`
- Content-Type: `application/json`
- Auth (v1): `device-login` (PIN/magic-link flow can be finalized later) with short-lived access token + refresh flow

## Status model

- `pending`
- `confirmed`
- `skipped`

## Endpoints

1. `POST /api/v1/auth/device-login`
2. `GET /api/v1/me/schedule`
3. `PUT /api/v1/me/schedule`
4. `GET /api/v1/me/events?from=YYYY-MM-DD&to=YYYY-MM-DD`
5. `POST /api/v1/me/events`
6. `POST /api/v1/me/push/subscribe`
7. `DELETE /api/v1/me/push/subscribe/{id}`
8. `POST /api/v1/sync/pull`
9. `POST /api/v1/sync/push`
10. `GET /livez`
11. `GET /readyz`

## Idempotency rule for `POST /api/v1/me/events`

- Client sends header `Idempotency-Key: <uuid>`.
- Server stores key hash + response fingerprint for a TTL window.
- Repeated request with same key returns original success response.

## Conflict rule (draft)

- Last-write-wins by `revision`, with guard:
  - no downgrade from `confirmed` to `pending`
  - no downgrade from `skipped` to `pending`

## Time fields

- All timestamps in API payloads are ISO-8601 UTC (`...Z`).
- Client local rendering uses user timezone (default `Europe/Moscow`).

## Language policy for API messages

- Пользовательские сообщения об ошибках в v1: русский язык.

## Push payload contract (for PWA deeplink)

Push `data` includes:

- `type`: `primary | nag`
- `day_key`: `YYYY-MM-DD`
- `slot`: `HH:MM`
- `nag_count`: number
- `url`: deeplink path, format `/?screen=today&day=<day_key>&slot=<slot>`

## Device login extensions

`POST /auth/device-login` can include optional fallback fields:

- `email`
- `notify_email_enabled`
