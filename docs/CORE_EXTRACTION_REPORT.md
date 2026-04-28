# Core Extraction Report

## Goal

Extract business logic from Telegram-specific implementation into pure backend core modules.

## Source mapping

1. `bot.py:56 parse_times` -> `backend/app/core/schedule.py::parse_times`
2. `bot.py:119 get_user_slots` (+ default slot behavior) -> `backend/app/core/schedule.py::normalize_slots` + `DEFAULT_SLOTS`
3. `bot.py:328 build_calendar_text_and_keyboard` (aggregation part) -> `backend/app/core/calendar.py::aggregate_week`
4. `bot.py:639 schedule_nag_and_escalation` (timing rules) -> `backend/app/core/reminders.py::build_followup_plan`
5. `bot.py:737 send_nag_reminder` (nag count and stop conditions) -> `should_send_nag`, `next_nag_count`, `should_stop_followups`
6. `bot.py:882 handle_callback` (status conflict safety) -> `backend/app/core/status.py::merge_status`, `apply_event_update`
7. `bot.py:503 validate_reschedule_values` -> `backend/app/core/schedule.py::validate_three_daily_slots`

## Core modules

- `backend/app/core/schedule.py`
- `backend/app/core/calendar.py`
- `backend/app/core/reminders.py`
- `backend/app/core/status.py`

## Deterministic tests

- `backend/tests/core/test_schedule.py`
- `backend/tests/core/test_calendar.py`
- `backend/tests/core/test_reminders.py`
- `backend/tests/core/test_status.py`

## Verification

- `python -m pytest -q` -> all tests pass.

