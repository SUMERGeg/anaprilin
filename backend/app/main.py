from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api import api_router
from app.config import settings
from app.db import engine, init_db
from app.logging_config import setup_logging
from app.scheduler import ReminderScheduler

setup_logging()
reminder_scheduler = ReminderScheduler()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_db:
        init_db()
    reminder_scheduler.start()
    yield
    reminder_scheduler.shutdown()


app = FastAPI(
    title="Anaprilin API",
    version="v1",
    description="API for offline-first Anaprilin reminders PWA.",
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/readyz")
def readyz() -> dict[str, object]:
    db_ok = False
    db_error: str | None = None
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = repr(exc)

    scheduler_ok = reminder_scheduler.is_running
    ready = db_ok and scheduler_ok
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "db_ok": db_ok,
                "db_error": db_error,
                "scheduler_running": scheduler_ok,
                "scheduler_last_tick_started_at": (
                    reminder_scheduler.last_tick_started_at.isoformat()
                    if reminder_scheduler.last_tick_started_at
                    else None
                ),
                "scheduler_last_tick_finished_at": (
                    reminder_scheduler.last_tick_finished_at.isoformat()
                    if reminder_scheduler.last_tick_finished_at
                    else None
                ),
                "scheduler_last_tick_error": reminder_scheduler.last_tick_error,
            },
        )

    return {
        "status": "ready",
        "db_ok": db_ok,
        "scheduler_running": scheduler_ok,
        "scheduler_last_tick_started_at": (
            reminder_scheduler.last_tick_started_at.isoformat()
            if reminder_scheduler.last_tick_started_at
            else None
        ),
        "scheduler_last_tick_finished_at": (
            reminder_scheduler.last_tick_finished_at.isoformat()
            if reminder_scheduler.last_tick_finished_at
            else None
        ),
        "scheduler_last_tick_error": reminder_scheduler.last_tick_error,
    }
