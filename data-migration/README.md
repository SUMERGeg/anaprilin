# Data Migration

Scripts:

- `import_confirmations.py`
- `import_subscribers.py`
- `verify_last_30_days.py`

Rules:

- Import only slots matching `HH:MM` as production intake events.
- `ТЕСТ-*` and `НАГ-*`:
  - default: skip
  - optional: `--import-debug-rows` -> import as `debug=true` + `status=skipped`

## Usage

Run from repository root:

```bash
python data-migration/import_subscribers.py
python data-migration/import_confirmations.py
python data-migration/verify_last_30_days.py
```

If you want to keep test/nag records in DB (debug mode):

```bash
python data-migration/import_confirmations.py --import-debug-rows
```

If verification finds mismatches, script exits with code `1`.
