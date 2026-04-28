from __future__ import annotations

import os


class Settings:
    api_v1_prefix: str = "/api/v1"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./anaprilin.db")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
    idempotency_ttl_hours: int = int(os.getenv("IDEMPOTENCY_TTL_HOURS", "24"))
    auto_create_db: bool = os.getenv("AUTO_CREATE_DB", "1") == "1"


settings = Settings()

