# Foundation Decisions (Confirmed)

These decisions are confirmed for current implementation.

1. Repository name/root: `anaprilin_ios`.
2. API v1 prefix: `/api/v1`.
3. Statuses: `pending`, `confirmed`, `skipped`.
4. Timezone default: `Europe/Moscow`.
5. Canonical DB timestamps: UTC.
6. `POST /me/events` uses `Idempotency-Key` header.
7. Conflict handling: last-write-wins with no downgrade to `pending`.
8. OpenAPI draft stored in `docs/openapi-v1.yaml`.
9. Docker setup is included now and can be refined later.
10. API error messages language: Russian.
