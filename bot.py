from __future__ import annotations
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Sequence
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from storage import ConfirmationStorage, SubscribersStorage, ReminderMessagesStorage, UsedImagesStorage

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class ReminderConfig:
    token: str
    timezone: ZoneInfo
    reminder_times: Sequence[time]
    data_file: Path

    @property
    def tz_aware_now(self) -> datetime:
        return datetime.now(self.timezone)


def parse_times(raw: str) -> List[time]:
    values = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hours, minutes = map(int, chunk.split(":"))
            values.append(time(hour=hours, minute=minutes))
        except ValueError as exc:
            raise ValueError(f"Неверный формат времени '{chunk}'. Используйте HH:MM.") from exc
    if len(values) == 0:
        raise ValueError("Нужно указать хотя бы одно время напоминания.")
    return values


def load_config() -> ReminderConfig:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN обязательна.")

    tz_name = os.environ.get("TIMEZONE", "Europe/Moscow")
    try:
        timezone = ZoneInfo(tz_name)
    except Exception as exc:  # pragma: no cover - ZoneInfo errors are rare
        raise RuntimeError(f"Неизвестный часовой пояс '{tz_name}'.") from exc

    times_raw = os.environ.get("REMINDER_TIMES", "09:00,15:00,21:00")
    reminder_times = parse_times(times_raw)

    data_file = Path(os.environ.get("DATA_FILE", "data/confirmations.json"))

    return ReminderConfig(
        token=token,
        timezone=timezone,
        reminder_times=tuple(sorted(reminder_times)),
        data_file=data_file,
    )


CONFIG = load_config()
STORAGE = ConfirmationStorage(CONFIG.data_file)
SUBSCRIBERS = SubscribersStorage(CONFIG.data_file.parent / "subscribers.json")
REMINDER_MESSAGES = ReminderMessagesStorage()
USED_IMAGES = UsedImagesStorage(CONFIG.data_file.parent / "used_images.json")

# Папка с картинками для напоминаний
IMAGES_DIR = BASE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# Админы бота (могут использовать тестовые команды)
ADMIN_USERNAMES = {"stapg"}


def make_day_key(chat_id: int, date_key: str) -> str:
    return f"{chat_id}:{date_key}"


def is_admin(update: Update) -> bool:
    """Проверяет, является ли пользователь админом."""
    user = update.effective_user
    if user is None:
        return False
    # Сравниваем без учёта регистра
    username = (user.username or "").lower()
    return username in ADMIN_USERNAMES


def get_random_image() -> Path | None:
    """Возвращает случайную неиспользованную картинку из папки images/ или None."""
    if not IMAGES_DIR.exists():
        return None
    
    all_images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg")) + \
                 list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.gif"))
    
    if not all_images:
        return None
    
    # Фильтруем уже использованные
    used = USED_IMAGES.get_used()
    available = [img for img in all_images if img.name not in used]
    
    # Если все использованы — сбрасываем и начинаем заново
    if not available:
        logger.info("Все картинки использованы, сбрасываю счётчик")
        USED_IMAGES.reset()
        available = all_images
    
    # Выбираем случайную и помечаем как использованную
    chosen = random.choice(available)
    USED_IMAGES.mark_used(chosen.name)
    
    return chosen


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or update.message is None:
        return

    # Логируем входящую команду
    username = user.username if user else "Unknown"
    logger.info(f"Получена команда /start от {username} (chat_id={chat.id})")

    is_new = not SUBSCRIBERS.contains(chat.id)
    SUBSCRIBERS.add(chat.id)
    times_text = ", ".join(t.strftime("%H:%M") for t in CONFIG.reminder_times)
    header = "💕 Привет, Лизочка!" if is_new else "✨ Настройки обновлены, солнышко!"
    
    await update.message.reply_text(
        f"{header}\n\n"
        f"Я буду напоминать тебе принять Анаприлин каждый день в {times_text}. "
        f"Это важно для твоего здоровья, и я буду рядом, чтобы ты не забыла! 💊\n\n"
        f"Если вдруг забудешь ответить, я мягко напомню ещё раз каждые 10 минут в течение часа. "
        f"Я забочусь о тебе! 🥰\n\n"
        "Команды:\n"
        "/status — посмотреть, как идут дела сегодня\n"
        "/calendar — календарь с твоей статистикой\n"
        "/test — проверить, как работают напоминания\n"
        "/stop — отключить напоминания (но лучше не надо! 😊)",
    )
    logger.info(f"Ответ на /start отправлен для {username}")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if SUBSCRIBERS.contains(chat.id):
        SUBSCRIBERS.remove(chat.id)
        await update.message.reply_text(
            "😢 Хорошо, Лизочка, я перестану напоминать...\n"
            "Но помни, что таблетки важны для твоего здоровья! ❤️\n\n"
            "Если передумаешь, просто напиши /start — я всегда рядом! 🤗"
        )
    else:
        await update.message.reply_text(
            "Солнышко, ты ещё не подписана на напоминания! 😊\n"
            "Напиши /start, и я буду заботиться о том, чтобы ты не забывала про таблетки. 💕"
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if not SUBSCRIBERS.contains(chat.id):
        await update.message.reply_text(
            "Лизонька, ты ещё не подписана на напоминания! 😊\n"
            "Напиши /start, чтобы я могла заботиться о тебе. 💕"
        )
        return

    today_key = CONFIG.tz_aware_now.strftime("%Y-%m-%d")
    statuses = STORAGE.list_day(make_day_key(chat.id, today_key))
    if not statuses:
        await update.message.reply_text("Сегодня напоминаний ещё не было, солнышко! ☀️")
        return

    lines = ["💊 Как дела с таблеточками сегодня, Лизочка:\n"]
    for item in statuses:
        emoji = {"pending": "⏳", "confirmed": "✅", "skipped": "⚠️"}.get(item.status, "❔")
        status_text = {
            "pending": "жду ответа",
            "confirmed": "принято",
            "skipped": "пропущено"
        }.get(item.status, item.status)
        lines.append(f"{emoji} {item.slot} — {status_text}")
    await update.message.reply_text("\n".join(lines))


def build_calendar_text_and_keyboard(chat_id: int, week_offset: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """Строит текст календаря за неделю и клавиатуру с кнопками навигации."""
    now = CONFIG.tz_aware_now
    
    # Вычисляем начало недели (понедельник)
    start_of_week = now - timedelta(days=now.weekday()) - timedelta(weeks=week_offset)
    
    lines = [f"📅 Твоя статистика, Лизочка! 💕\n"]
    
    # Формируем диапазон дат для отображения
    week_start_str = start_of_week.strftime("%d.%m")
    week_end = start_of_week + timedelta(days=6)
    week_end_str = week_end.strftime("%d.%m")
    lines.append(f"Неделя: {week_start_str} — {week_end_str}\n")
    
    # Показываем 7 дней (неделя)
    for day_idx in range(7):
        date = start_of_week + timedelta(days=day_idx)
        day_key = date.strftime("%Y-%m-%d")
        statuses = STORAGE.list_day(make_day_key(chat_id, day_key))
        
        # Подсчитываем количество подтверждённых таблеток
        confirmed_count = sum(1 for item in statuses if item.status == "confirmed")
        
        # Выбираем эмодзи в зависимости от количества
        if confirmed_count == 0:
            emoji = "⚫"  # Черный - 0 таблеток
        elif confirmed_count == 1:
            emoji = "🔴"  # Красный - 1 таблетка
        elif confirmed_count == 2:
            emoji = "🟡"  # Желтый - 2 таблетки
        else:
            emoji = "🟢"  # Зеленый - 3+ таблетки
        
        # Форматируем дату
        date_str = date.strftime("%d.%m")
        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
        
        lines.append(f"{emoji} {date_str} ({weekday}) — {confirmed_count}/3")
    
    lines.append("\n⚫ 0 таблеток | 🔴 1 таблетка | 🟡 2 таблетки | 🟢 3 таблетки")
    
    # Создаём кнопки навигации
    keyboard = [
        [
            InlineKeyboardButton("← Предыдущая", callback_data=f"cal_week|{week_offset + 1}"),
            InlineKeyboardButton("Следующая →", callback_data=f"cal_week|{week_offset - 1}"),
        ]
    ]
    
    # Отключаем кнопку "Следующая", если это текущая неделя
    if week_offset <= 0:
        keyboard[0][1] = InlineKeyboardButton("—", callback_data="cal_noop")
    
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает календарь с цветовой индикацией по дням."""
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if not SUBSCRIBERS.contains(chat.id):
        await update.message.reply_text(
            "Лизонька, ты ещё не подписана! 😊\n"
            "Напиши /start, и я буду заботиться о тебе. 💕"
        )
        return

    text, keyboard = build_calendar_text_and_keyboard(chat.id, week_offset=0)
    await update.message.reply_text(text, reply_markup=keyboard)


async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if not SUBSCRIBERS.contains(chat.id):
        await update.message.reply_text(
            "Солнышко, сначала подпишись! 🥰\n"
            "Напиши /start, пожалуйста. 💕"
        )
        return

    now = CONFIG.tz_aware_now
    day_key = now.strftime("%Y-%m-%d")
    slot = f"ТЕСТ-{now.strftime('%H:%M')}"
    timestamp = now.isoformat()

    STORAGE.mark_sent(make_day_key(chat.id, day_key), slot, timestamp)
    
    period = get_period_name(slot)
    text = f"🧪 Тестовое напоминание, Лизочка!\n\n💊 Выпила таблеточку {period}?"

    message = await update.message.reply_text(
        text=text,
        reply_markup=build_keyboard(day_key, slot, chat.id),
    )

    # Планируем первое напоминание через 10 минут
    context.job_queue.run_once(
        send_nag_reminder,
        when=timedelta(minutes=10),
        name=f"nag-{chat.id}-{day_key}-{slot}-1",
        data={
            "day_key": day_key,
            "slot": slot,
            "chat_id": chat.id,
            "nag_count": 1,
        },
    )


def get_period_name(slot_time: str) -> str:
    """Определяет название периода дня по времени."""
    # Извлекаем время из слота (может быть "ТЕСТ-23:00" или "12:00")
    time_part = slot_time.split("-")[-1] if "-" in slot_time else slot_time
    try:
        hour = int(time_part.split(":")[0])
    except (ValueError, IndexError):
        return "сегодня"
    
    if 5 <= hour < 14:
        return "утром"
    elif 14 <= hour < 20:
        return "днем"
    else:
        return "вечером"


def build_keyboard(day_key: str, slot: str, chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Выпила",
                    callback_data=f"confirm|{chat_id}|{day_key}|{slot}",
                ),
                InlineKeyboardButton(
                    "⚠️ Пропустить",
                    callback_data=f"skip|{chat_id}|{day_key}|{slot}",
                ),
            ]
        ]
    )


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    slot: str = context.job.data["slot"]
    now = CONFIG.tz_aware_now
    day_key = now.strftime("%Y-%m-%d")
    timestamp = now.isoformat()

    subscribers = SUBSCRIBERS.get_all()
    if not subscribers:
        logger.debug("Нет активных подписчиков — пропускаю напоминание %s.", slot)
        return

    period = get_period_name(slot)
    
    # Милые вариации напоминаний в зависимости от времени суток
    morning_texts = [
        f"💕 Доброе утро, Лизочка!\n\nНе забудь принять таблеточку Анаприлина, солнышко. Это важно для твоего здоровья! 💊",
        f"☀️ Привет, моя хорошая!\n\nВремя выпить утреннюю таблетку Анаприлина. Я забочусь о тебе! 💊💕",
    ]
    afternoon_texts = [
        f"🌸 Лизонька, привет!\n\nПора принять дневную таблетку Анаприлина. Не забудь, пожалуйста! 💊",
        f"💐 Как дела, солнышко?\n\nНапоминаю про дневную таблеточку Анаприлина. Береги себя! 💊💕",
    ]
    evening_texts = [
        f"🌙 Добрый вечер, Лизочка!\n\nПора принять вечернюю таблетку Анаприлина. Я рядом! 💊",
        f"✨ Милая, не забудь вечернюю таблеточку Анаприлина. Это важно! 💊💕",
    ]
    
    if period == "утром":
        text = random.choice(morning_texts)
    elif period == "днем":
        text = random.choice(afternoon_texts)
    else:
        text = random.choice(evening_texts)

    for chat_id in subscribers:
        STORAGE.mark_sent(make_day_key(chat_id, day_key), slot, timestamp)
        
        # Отправляем текстовое напоминание (без картинок для стабильности)
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=build_keyboard(day_key, slot, chat_id),
        )
        
        # Сохраняем message_id для последующего удаления
        REMINDER_MESSAGES.add_message(chat_id, day_key, slot, message.message_id)

        # Планируем первое напоминание через 10 минут
        context.job_queue.run_once(
            send_nag_reminder,
            when=timedelta(minutes=10),
            name=f"nag-{chat_id}-{day_key}-{slot}-1",
            data={
                "day_key": day_key,
                "slot": slot,
                "chat_id": chat_id,
                "nag_count": 1,
            },
        )


async def send_nag_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет повторное напоминание 'Не забудь ответить' если пользователь еще не подтвердил."""
    data = context.job.data
    day_key = data["day_key"]
    slot = data["slot"]
    chat_id = data["chat_id"]
    nag_count = data.get("nag_count", 1)

    chat_day_key = make_day_key(chat_id, day_key)
    statuses = STORAGE.list_day(chat_day_key)
    slot_status = next((item for item in statuses if item.slot == slot), None)
    
    # Если уже подтвердили или пропустили - ничего не делаем
    if not slot_status or slot_status.status != "pending":
        return

    # Отправляем напоминание
    period = get_period_name(slot)
    
    # Милые варианты повторных напоминаний
    nag_texts = [
        f"💕 Лизочка, ты ещё не ответила!\n\nВыпила таблеточку {period}? Дай мне знать, пожалуйста! 💊",
        f"🥰 Солнышко, напоминаю!\n\nНе забудь подтвердить, что выпила таблетку {period}. Я волнуюсь! 💊",
        f"💝 Лизонька, отзовись!\n\nТы приняла таблетку {period}? Очень важно! 💊",
        f"🌸 Моя хорошая, не забудь ответить!\n\nВыпила Анаприлин {period}? Это для твоего здоровья! 💊",
    ]
    
    text = random.choice(nag_texts)
    
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=build_keyboard(day_key, slot, chat_id),
    )
    
    # Сохраняем message_id для последующего удаления
    REMINDER_MESSAGES.add_message(chat_id, day_key, slot, message.message_id)

    # Планируем следующее напоминание через 10 минут, но не более 6 раз (1 час)
    if nag_count < 6:
        context.job_queue.run_once(
            send_nag_reminder,
            when=timedelta(minutes=10),
            name=f"nag-{chat_id}-{day_key}-{slot}-{nag_count + 1}",
            data={
                "day_key": day_key,
                "slot": slot,
                "chat_id": chat_id,
                "nag_count": nag_count + 1,
            },
        )


def cancel_nag_reminders(context: ContextTypes.DEFAULT_TYPE, chat_id: int, day_key: str, slot: str) -> None:
    """Отменяет все запланированные повторные напоминания для данного слота."""
    job_queue = context.job_queue
    if job_queue is None:
        return
    
    # Ищем и удаляем все задачи, которые начинаются с nag-{chat_id}-{day_key}-{slot}
    prefix = f"nag-{chat_id}-{day_key}-{slot}-"
    jobs_to_remove = [job for job in job_queue.jobs() if job.name and job.name.startswith(prefix)]
    
    for job in jobs_to_remove:
        job.schedule_removal()
        logger.debug(f"Отменена задача напоминания: {job.name}")


async def delete_reminder_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int, day_key: str, slot: str, except_message_id: int | None = None) -> str | None:
    """Удаляет все сообщения напоминаний для данного слота и возвращает file_id картинки."""
    message_ids, photo_file_id = REMINDER_MESSAGES.clear_messages(chat_id, day_key, slot)
    
    for msg_id in message_ids:
        if msg_id == except_message_id:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.debug(f"Удалено сообщение {msg_id} для {chat_id}")
        except BadRequest as e:
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
    
    return photo_file_id


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data is None:
        await query.answer("Ошибка обработки запроса.")
        return
    
    # Обработка календаря
    if query.data.startswith("cal_week|"):
        try:
            week_offset = int(query.data.split("|")[1])
            chat_id = query.message.chat_id if query.message else None
            if chat_id is None:
                await query.answer("Ошибка получения чата.")
                return
            
            text, keyboard = build_calendar_text_and_keyboard(chat_id, week_offset)
            await query.edit_message_text(text, reply_markup=keyboard)
            await query.answer()
        except (ValueError, IndexError):
            await query.answer("Ошибка навигации.")
        return
    
    # Заглушка для неактивных кнопок
    if query.data == "cal_noop":
        await query.answer()
        return
    
    # Обработка подтверждений приёма таблеток
    await query.answer()
    try:
        action, chat_id_raw, day_key, slot = query.data.split("|", 3)
        chat_id = int(chat_id_raw)
    except ValueError:
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    message_chat_id = query.message.chat_id if query.message else None
    if message_chat_id != chat_id:
        await query.answer("Кнопка больше неактуальна.", show_alert=True)
        return

    chat_day_key = make_day_key(chat_id, day_key)
    current_message_id = query.message.message_id if query.message else None
    
    if action == "confirm":
        STORAGE.mark_confirmed(chat_day_key, slot, CONFIG.tz_aware_now.isoformat())
        
        # Милые варианты подтверждения
        confirm_texts = [
            "✅ Отлично, Лизочка! Молодец, что выпила таблетку! 💕\n\nЯ горжусь тобой! 🥰",
            "✅ Супер, солнышко! Таблетка принята! 💊\n\nТы умничка! 💕",
            "✅ Ура! Спасибо, что позаботилась о своём здоровье! 💕\n\nЛюблю тебя, Лизочка! 🥰",
            "✅ Прекрасно, моя хорошая! Таблетка принята! 💊\n\nТы — самая лучшая! 💕",
        ]
        
        # Удаляем все другие сообщения напоминаний
        await delete_reminder_messages(context, chat_id, day_key, slot, except_message_id=current_message_id)
        
        # Отправляем финальное сообщение и удаляем текущее
        confirm_text = random.choice(confirm_texts)
        await context.bot.send_message(chat_id=chat_id, text=confirm_text)
        
        try:
            await query.message.delete()
        except BadRequest:
            pass
        
        # Отменяем все запланированные напоминания для этого слота
        cancel_nag_reminders(context, chat_id, day_key, slot)
    elif action == "skip":
        STORAGE.mark_skipped(chat_day_key, slot, CONFIG.tz_aware_now.isoformat())
        
        # Удаляем все другие сообщения напоминаний
        await delete_reminder_messages(context, chat_id, day_key, slot, except_message_id=current_message_id)
        
        skip_text = (
            "😔 Лизочка, ты пропустила таблетку...\n\n"
            "Пожалуйста, постарайся не забывать! Это важно для твоего здоровья. ❤️"
        )
        
        # Отправляем финальное сообщение и удаляем текущее
        await context.bot.send_message(chat_id=chat_id, text=skip_text)
        try:
            await query.message.delete()
        except BadRequest:
            pass
        
        # Отменяем все запланированные напоминания для этого слота
        cancel_nag_reminders(context, chat_id, day_key, slot)
    else:
        await query.edit_message_text("Что-то пошло не так... 🤔")


# ==================== АДМИНСКИЕ КОМАНДЫ ====================

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список админских команд."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    await update.message.reply_text(
        "🔧 Админские команды:\n\n"
        "/admin — это меню\n"
        "/atest — тестовое напоминание (с картинкой)\n"
        "/atest_nag — тестовое повторное напоминание\n"
        "/astatus — статус бота и подписчиков\n"
        "/asubs — список подписчиков\n"
        "/abroadcast [текст] — сообщение всем\n"
        "/aclear_day — инфо об очистке данных\n"
        "/aimages — статистика картинок\n"
        "/aimages_reset — сбросить использованные"
    )


async def admin_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет тестовое напоминание."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    chat = update.effective_chat
    now = CONFIG.tz_aware_now
    day_key = now.strftime("%Y-%m-%d")
    slot = f"ТЕСТ-{now.strftime('%H:%M:%S')}"
    timestamp = now.isoformat()
    period = get_period_name(slot)
    
    STORAGE.mark_sent(make_day_key(chat.id, day_key), slot, timestamp)
    
    text = f"🧪 Тестовое напоминание (админ)\n\n💊 Лизочка, выпила таблеточку {period}?"
    
    message = await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_markup=build_keyboard(day_key, slot, chat.id),
    )
    await update.message.reply_text("✅ Тестовое напоминание отправлено!")
    
    REMINDER_MESSAGES.add_message(chat.id, day_key, slot, message.message_id)
    
    # Планируем повторное напоминание через 1 минуту (для тестов)
    context.job_queue.run_once(
        send_nag_reminder,
        when=timedelta(minutes=1),
        name=f"nag-{chat.id}-{day_key}-{slot}-1",
        data={
            "day_key": day_key,
            "slot": slot,
            "chat_id": chat.id,
            "nag_count": 1,
        },
    )


async def admin_test_nag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет тестовое повторное напоминание."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    chat = update.effective_chat
    now = CONFIG.tz_aware_now
    day_key = now.strftime("%Y-%m-%d")
    slot = f"НАГ-{now.strftime('%H:%M:%S')}"
    timestamp = now.isoformat()
    period = get_period_name(slot)
    
    STORAGE.mark_sent(make_day_key(chat.id, day_key), slot, timestamp)
    
    text = f"🔔 **Тестовое повторное напоминание**\n\n💕 Лизочка, ты ещё не ответила! Выпила таблеточку {period}?"
    
    message = await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_markup=build_keyboard(day_key, slot, chat.id),
        parse_mode="Markdown"
    )
    
    REMINDER_MESSAGES.add_message(chat.id, day_key, slot, message.message_id)
    await update.message.reply_text("✅ Отправлено повторное напоминание")


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статус бота."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    subs = SUBSCRIBERS.get_all()
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg")) + \
             list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.gif"))
    
    times_text = ", ".join(t.strftime("%H:%M") for t in CONFIG.reminder_times)
    
    await update.message.reply_text(
        f"📊 **Статус бота:**\n\n"
        f"👥 Подписчиков: {len(subs)}\n"
        f"🖼 Картинок: {len(images)}\n"
        f"⏰ Времена напоминаний: {times_text}\n"
        f"🌍 Часовой пояс: {CONFIG.timezone}\n"
        f"📅 Сейчас: {CONFIG.tz_aware_now.strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode="Markdown"
    )


async def admin_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список подписчиков."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    subs = SUBSCRIBERS.get_all()
    if not subs:
        await update.message.reply_text("📭 Подписчиков пока нет.")
        return
    
    lines = ["👥 **Подписчики:**\n"]
    for chat_id in subs:
        lines.append(f"• `{chat_id}`")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение всем подписчикам."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи текст: /abroadcast Привет всем!")
        return
    
    text = " ".join(context.args)
    subs = SUBSCRIBERS.get_all()
    sent = 0
    
    for chat_id in subs:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить в {chat_id}: {e}")
    
    await update.message.reply_text(f"✅ Отправлено {sent}/{len(subs)} подписчикам")


async def admin_clear_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает данные за сегодня (для тестов)."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    chat = update.effective_chat
    today_key = CONFIG.tz_aware_now.strftime("%Y-%m-%d")
    chat_day_key = make_day_key(chat.id, today_key)
    
    # Просто пометим что данных нет (упрощённая очистка)
    await update.message.reply_text(
        f"🗑 Для полной очистки удали записи с ключом `{chat_day_key}` из `data/confirmations.json`.\n\n"
        f"Или используй /atest для создания новых тестовых напоминаний.",
        parse_mode="Markdown"
    )


async def admin_images(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о картинках."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg")) + \
             list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.gif"))
    
    used = USED_IMAGES.get_used()
    available = [img for img in images if img.name not in used]
    
    if not images:
        await update.message.reply_text(
            f"🖼 **Картинки:**\n\n"
            f"Папка: `{IMAGES_DIR}`\n"
            f"Картинок: 0\n\n"
            f"Добавь картинки (jpg, png, gif) в папку `images/` и они будут отправляться с первым напоминанием.",
            parse_mode="Markdown"
        )
        return
    
    lines = [
        f"🖼 **Картинки:**\n",
        f"📁 Всего: {len(images)}",
        f"✅ Доступно: {len(available)}",
        f"📤 Использовано: {len(used)}\n",
    ]
    
    # Показываем доступные
    if available:
        lines.append("**Доступные:**")
        for img in available[:10]:
            lines.append(f"• {img.name}")
        if len(available) > 10:
            lines.append(f"... и ещё {len(available) - 10}")
    
    lines.append("\n`/aimages_reset` — сбросить использованные")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_images_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сбрасывает список использованных картинок."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    count = len(USED_IMAGES.get_used())
    USED_IMAGES.reset()
    await update.message.reply_text(f"✅ Сброшено {count} использованных картинок. Теперь все снова доступны!")


def build_application() -> Application:
    # Быстрые таймауты для отправки сообщений (чтобы бот отвечал мгновенно)
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=5.0,
        read_timeout=5.0,
        write_timeout=5.0,
        pool_timeout=3.0,
    )
    
    # Для long polling нужен большой таймаут - это нормально
    get_updates_request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=5.0,
        read_timeout=60.0,  # Long polling ждёт до 60 сек - это ок
        write_timeout=5.0,
        pool_timeout=3.0,
    )
    
    app = (
        ApplicationBuilder()
        .token(CONFIG.token)
        .rate_limiter(AIORateLimiter(max_retries=3))  # Автоматический retry при ошибках
        .request(request)
        .get_updates_request(get_updates_request)
        .build()
    )
    if app.job_queue is None:
        raise RuntimeError(
            "JobQueue недоступен. Установите пакет с экстрами: "
            "`pip install \"python-telegram-bot[rate-limiter,job-queue]==20.8\"`."
        )
    
    # Устанавливаем часовой пояс для JobQueue
    app.job_queue.scheduler.timezone = CONFIG.timezone
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("calendar", calendar))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("test", test_reminder))
    
    # Админские команды
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("atest", admin_test_reminder))
    app.add_handler(CommandHandler("atest_nag", admin_test_nag))
    app.add_handler(CommandHandler("astatus", admin_status))
    app.add_handler(CommandHandler("asubs", admin_subscribers))
    app.add_handler(CommandHandler("abroadcast", admin_broadcast))
    app.add_handler(CommandHandler("aclear_day", admin_clear_day))
    app.add_handler(CommandHandler("aimages", admin_images))
    app.add_handler(CommandHandler("aimages_reset", admin_images_reset))
    
    app.add_handler(CallbackQueryHandler(handle_callback))

    for reminder_time in CONFIG.reminder_times:
        slot = reminder_time.strftime("%H:%M")
        app.job_queue.run_daily(
            send_reminder,
            time=reminder_time,
            days=(0, 1, 2, 3, 4, 5, 6),
            name=f"reminder-{slot}",
            data={"slot": slot},
        )
    return app


def main() -> None:
    logger.info("Запуск бота. Времена напоминаний: %s", ", ".join(t.strftime("%H:%M") for t in CONFIG.reminder_times))
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

