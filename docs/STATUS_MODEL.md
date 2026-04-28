# Status Model v1

## States

- `pending`: reminder was created/sent, user has not acted.
- `confirmed`: user confirmed intake.
- `skipped`: user explicitly skipped intake.

## Allowed transitions

1. `pending -> confirmed`
2. `pending -> skipped`
3. `confirmed -> confirmed` (idempotent repeat)
4. `skipped -> skipped` (idempotent repeat)

## Forbidden transitions

1. `confirmed -> pending`
2. `skipped -> pending`
3. `confirmed -> skipped` (unless future explicit manual correction flow is added)
4. `skipped -> confirmed` (unless future explicit manual correction flow is added)

## Notes

- Foundation keeps final states immutable from normal reminder flow.
- If correction UX is needed later, it should be implemented as a privileged/manual action with audit.

