from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.schedule import get_period_name
from app.models.users import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    from_email: str
    use_tls: bool
    timeout_seconds: int


def get_email_config() -> EmailConfig:
    return EmailConfig(
        host=os.getenv("SMTP_HOST"),
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USERNAME"),
        password=os.getenv("SMTP_PASSWORD"),
        from_email=os.getenv("SMTP_FROM_EMAIL", "anaprilin@localhost"),
        use_tls=os.getenv("SMTP_USE_TLS", "1") == "1",
        timeout_seconds=int(os.getenv("SMTP_TIMEOUT_SECONDS", "10")),
    )


def can_send_email(user: User) -> bool:
    return bool(user.notify_email_enabled and user.email)


def _build_subject_and_body(*, day_key: str, slot: str, is_nag: bool, nag_count: int) -> tuple[str, str]:
    period = get_period_name(slot)
    if is_nag:
        subject = "Напоминание: подтвердите прием"
        body = (
            f"Слот {slot} ({period}), дата {day_key}.\n"
            f"Это повторное напоминание №{nag_count}. "
            "Пожалуйста, откройте приложение и отметьте прием."
        )
    else:
        subject = "Напоминание о приеме Анаприлина"
        body = (
            f"Слот {slot} ({period}), дата {day_key}.\n"
            "Откройте приложение и отметьте прием."
        )
    return subject, body


def send_email_fallback(
    user: User,
    *,
    day_key: str,
    slot: str,
    is_nag: bool,
    nag_count: int,
) -> bool:
    if not can_send_email(user):
        return False

    cfg = get_email_config()
    if not cfg.host:
        logger.warning("SMTP_HOST не задан; email fallback отключен.")
        return False

    assert user.email is not None
    subject, body = _build_subject_and_body(day_key=day_key, slot=slot, is_nag=is_nag, nag_count=nag_count)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.from_email
    msg["To"] = user.email
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_seconds) as smtp:
            if cfg.use_tls:
                smtp.starttls()
            if cfg.username and cfg.password:
                smtp.login(cfg.username, cfg.password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # pragma: no cover - network/remote behavior
        logger.warning("Email fallback failed for user=%s: %r", user.id, exc)
        return False

