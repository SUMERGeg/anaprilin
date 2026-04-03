from __future__ import annotations
import io
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Sequence
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import asyncio
from PIL import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from storage import ConfirmationStorage, SubscribersStorage, ReminderMessagesStorage, UserSettingsStorage

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
# Иначе httpx пишет полный URL с BOT_TOKEN в journalctl
logging.getLogger("httpx").setLevel(logging.WARNING)
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
USER_SETTINGS = UserSettingsStorage(CONFIG.data_file.parent / "user_settings.json")
ESCALATION_TARGET = os.environ.get("ESCALATION_TARGET", "@stapg")

# Папка с картинками для напоминаний
IMAGES_DIR = BASE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# Админы бота (могут использовать тестовые команды)
ADMIN_USERNAMES = {"stapg"}


def make_day_key(chat_id: int, date_key: str) -> str:
    return f"{chat_id}:{date_key}"


def get_default_slots() -> List[str]:
    return [t.strftime("%H:%M") for t in CONFIG.reminder_times]


def get_user_slots(chat_id: int) -> List[str]:
    return USER_SETTINGS.get_times(chat_id) or get_default_slots()


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 В главное меню", callback_data="menu_main")]]
    )


def is_admin(update: Update) -> bool:
    """Проверяет, является ли пользователь админом."""
    user = update.effective_user
    if user is None:
        return False
    # Сравниваем без учёта регистра
    username = (user.username or "").lower()
    return username in ADMIN_USERNAMES


async def send_with_retry(bot, chat_id: int, text: str, max_retries: int = 5, **kwargs):
    """Отправляет сообщение с повторными попытками при таймаутах."""
    for attempt in range(max_retries):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except (TimedOut, NetworkError) as e:
            wait_time = (attempt + 1) * 2  # 2, 4, 6, 8, 10 секунд
            logger.warning(f"Таймаут при отправке в {chat_id}, попытка {attempt + 1}/{max_retries}, жду {wait_time}с: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отправить сообщение в {chat_id} после {max_retries} попыток")
                raise
    return None


def compress_image(photo_path: Path, max_size: int = 1280, quality: int = 85) -> io.BytesIO:
    """Сжимает изображение до указанного размера и качества, возвращает байты."""
    with Image.open(photo_path) as img:
        # Конвертируем в RGB если нужно (для PNG с альфа-каналом)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Уменьшаем размер если больше max_size
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Сохраняем в буфер как JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)
        return buffer


async def send_photo_with_retry(bot, chat_id: int, photo_path: Path, caption: str, max_retries: int = 5, **kwargs):
    """Отправляет сжатое фото с подписью с повторными попытками при таймаутах."""
    # Сжимаем картинку один раз перед отправкой
    try:
        compressed = compress_image(photo_path)
    except Exception as e:
        logger.warning(f"Не удалось сжать изображение {photo_path}: {e}, отправляю оригинал")
        compressed = None
    
    for attempt in range(max_retries):
        try:
            if compressed:
                compressed.seek(0)  # Сбрасываем позицию для повторной отправки
                return await bot.send_photo(chat_id=chat_id, photo=compressed, caption=caption, **kwargs)
            else:
                with open(photo_path, "rb") as photo_file:
                    return await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption, **kwargs)
        except (TimedOut, NetworkError) as e:
            wait_time = (attempt + 1) * 2
            logger.warning(f"Таймаут при отправке фото в {chat_id}, попытка {attempt + 1}/{max_retries}, жду {wait_time}с: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отправить фото в {chat_id} после {max_retries} попыток")
                raise
    return None


def get_random_image() -> Path | None:
    """Возвращает случайную картинку из папки images/ или None."""
    if not IMAGES_DIR.exists():
        return None
    
    all_images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg")) + \
                 list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.gif"))
    
    if not all_images:
        return None
    
    return random.choice(all_images)


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
    times_text = ", ".join(get_user_slots(chat.id))
    header = "💕 Привет, Лизочка!" if is_new else "✨ Настройки обновлены, солнышко!"
    
    text = (
        f"{header}\n\n"
        f"Я буду напоминать тебе принять Анаприлин каждый день в {times_text}. "
        f"Это важно для твоего здоровья, и я буду рядом, чтобы ты не забыла! 💊\n\n"
        f"Если вдруг забудешь ответить, я мягко напомню ещё раз каждые 10 минут в течение часа. "
        f"Я забочусь о тебе! 🥰\n\n"
        "Используй кнопки ниже — так удобнее 💕"
    )

    await send_with_retry(context.bot, chat.id, text, reply_markup=build_start_menu_keyboard())
    logger.info(f"Ответ на /start отправлен для {username}")


def build_start_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Статус", callback_data="menu_status"),
                InlineKeyboardButton("📅 Календарь", callback_data="menu_calendar"),
            ],
            [
                InlineKeyboardButton("🧪 Тест", callback_data="menu_test"),
                InlineKeyboardButton("⏰ Расписание", callback_data="menu_reschedule_help"),
            ],
            [
                InlineKeyboardButton("🛑 Стоп", callback_data="menu_stop"),
            ],
        ]
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if SUBSCRIBERS.contains(chat.id):
        SUBSCRIBERS.remove(chat.id)
        await send_with_retry(
            context.bot, chat.id,
            "😢 Хорошо, Лизочка, я перестану напоминать...\n"
            "Но помни, что таблетки важны для твоего здоровья! ❤️\n\n"
            "Если передумаешь, просто напиши /start — я всегда рядом! 🤗"
        )
    else:
        await send_with_retry(
            context.bot, chat.id,
            "Солнышко, ты ещё не подписана на напоминания! 😊\n"
            "Напиши /start, и я буду заботиться о том, чтобы ты не забывала про таблетки. 💕"
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    await send_status(context, chat.id)

async def send_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not SUBSCRIBERS.contains(chat_id):
        await send_with_retry(
            context.bot, chat_id,
            "Лизонька, ты ещё не подписана на напоминания! 😊\n"
            "Напиши /start, чтобы я могла заботиться о тебе. 💕",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    today_key = CONFIG.tz_aware_now.strftime("%Y-%m-%d")
    statuses = STORAGE.list_day(make_day_key(chat_id, today_key))
    if not statuses:
        await send_with_retry(
            context.bot,
            chat_id,
            "Сегодня напоминаний ещё не было, солнышко! ☀️",
            reply_markup=build_back_to_menu_keyboard(),
        )
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
    await send_with_retry(
        context.bot,
        chat_id,
        "\n".join(lines),
        reply_markup=build_back_to_menu_keyboard(),
    )


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

    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="menu_main")])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает календарь с цветовой индикацией по дням."""
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    await send_calendar(context, chat.id)

async def send_calendar(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not SUBSCRIBERS.contains(chat_id):
        await send_with_retry(
            context.bot, chat_id,
            "Лизонька, ты ещё не подписана! 😊\n"
            "Напиши /start, и я буду заботиться о тебе. 💕",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return
    text, keyboard = build_calendar_text_and_keyboard(chat_id, week_offset=0)
    await send_with_retry(context.bot, chat_id, text, reply_markup=keyboard)


async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    await send_test_reminder(context, chat.id, is_admin_test=False)

async def send_test_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int, is_admin_test: bool) -> None:
    if not SUBSCRIBERS.contains(chat_id):
        await send_with_retry(
            context.bot, chat_id,
            "Солнышко, сначала подпишись! 🥰\n"
            "Напиши /start, пожалуйста. 💕"
        )
        return

    now = CONFIG.tz_aware_now
    day_key = now.strftime("%Y-%m-%d")
    slot = f"ТЕСТ-{now.strftime('%H:%M')}"
    timestamp = now.isoformat()
    STORAGE.mark_sent(make_day_key(chat_id, day_key), slot, timestamp)

    period = get_period_name(slot)
    text = (
        f"🧪 Тестовое напоминание (админ)\n\n💊 Лизочка, выпила таблеточку {period}?"
        if is_admin_test
        else f"🧪 Тестовое напоминание, Лизочка!\n\n💊 Выпила таблеточку {period}?"
    )

    image_path = get_random_image()
    if image_path:
        message = await send_photo_with_retry(
            context.bot, chat_id, image_path, text,
            reply_markup=build_keyboard(day_key, slot, chat_id),
        )
    else:
        message = await send_with_retry(
            context.bot, chat_id, text,
            reply_markup=build_keyboard(day_key, slot, chat_id),
        )

    if message:
        REMINDER_MESSAGES.add_message(chat_id, day_key, slot, message.message_id)
    schedule_nag_and_escalation(context, chat_id, day_key, slot)


async def reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    if not SUBSCRIBERS.contains(chat.id):
        await send_with_retry(
            context.bot,
            chat.id,
            "Сначала нажми /start, чтобы включить напоминания.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return

    if not context.args:
        await begin_reschedule_flow(context, chat.id)
        return

    raw = " ".join(context.args).replace(" ", "")
    try:
        new_times = sorted(parse_times(raw))
    except ValueError as exc:
        await send_with_retry(context.bot, chat.id, f"⚠️ {exc}")
        return

    slots = [t.strftime("%H:%M") for t in new_times]
    USER_SETTINGS.set_times(chat.id, slots)
    cancel_all_followups_for_chat(context, chat.id)
    await send_with_retry(
        context.bot,
        chat.id,
        "✅ Новое расписание сохранено: " + ", ".join(slots),
        reply_markup=build_back_to_menu_keyboard(),
    )


async def begin_reschedule_flow(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    context.user_data["reschedule_step"] = "morning"
    context.user_data["reschedule_values"] = {}
    current = ", ".join(get_user_slots(chat_id))
    await send_with_retry(
        context.bot,
        chat_id,
        "⏰ Настройка расписания\n\n"
        f"Текущее: {current}\n\n"
        "Шаг 1/3: введи время *утреннего* приема в формате `HH:MM`",
        parse_mode="Markdown",
        reply_markup=build_back_to_menu_keyboard(),
    )


def validate_reschedule_values(values: dict[str, str]) -> str | None:
    keys = ("morning", "afternoon", "evening")
    if not all(k in values for k in keys):
        return "Заполнены не все значения."
    try:
        parsed = [parse_times(values[k])[0] for k in keys]
    except ValueError as exc:
        return str(exc)

    text_values = [v.strftime("%H:%M") for v in parsed]
    if len(set(text_values)) != 3:
        return "Время должно быть разным для всех трёх приёмов."
    if not (parsed[0] < parsed[1] < parsed[2]):
        return "Порядок должен быть: утро < день < вечер."
    return None


def build_reschedule_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Сохранить", callback_data="reschedule_save")],
            [InlineKeyboardButton("✏️ Изменить заново", callback_data="reschedule_restart")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="menu_main")],
        ]
    )


async def handle_reschedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    message = update.message
    if chat is None or message is None:
        return False

    step = context.user_data.get("reschedule_step")
    if step not in {"morning", "afternoon", "evening"}:
        return False

    raw = message.text.strip()
    try:
        parsed = parse_times(raw)
        if len(parsed) != 1:
            raise ValueError("Укажи только одно время в формате HH:MM")
        value = parsed[0].strftime("%H:%M")
    except ValueError as exc:
        await send_with_retry(
            context.bot,
            chat.id,
            f"⚠️ {exc}\nПопробуй еще раз.",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return True

    values = context.user_data.setdefault("reschedule_values", {})
    values[step] = value

    if step == "morning":
        context.user_data["reschedule_step"] = "afternoon"
        await send_with_retry(
            context.bot,
            chat.id,
            f"Утро: {value} ✅\n\nШаг 2/3: введи время *дневного* приема (`HH:MM`)",
            parse_mode="Markdown",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return True

    if step == "afternoon":
        context.user_data["reschedule_step"] = "evening"
        await send_with_retry(
            context.bot,
            chat.id,
            f"День: {value} ✅\n\nШаг 3/3: введи время *вечернего* приема (`HH:MM`)",
            parse_mode="Markdown",
            reply_markup=build_back_to_menu_keyboard(),
        )
        return True

    error = validate_reschedule_values(values)
    if error:
        await send_with_retry(
            context.bot,
            chat.id,
            "⚠️ Проверка не прошла:\n"
            f"{error}\n\n"
            "Нажми «Изменить заново» или вернись в меню.",
            reply_markup=build_reschedule_confirm_keyboard(),
        )
        return True

    context.user_data["reschedule_step"] = "confirm"
    await send_with_retry(
        context.bot,
        chat.id,
        "Проверь новое расписание:\n"
        f"🌅 Утро: {values['morning']}\n"
        f"🌤 День: {values['afternoon']}\n"
        f"🌙 Вечер: {values['evening']}",
        reply_markup=build_reschedule_confirm_keyboard(),
    )
    return True


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


def schedule_nag_and_escalation(context: ContextTypes.DEFAULT_TYPE, chat_id: int, day_key: str, slot: str) -> None:
    if context.job_queue is None:
        return
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
    context.job_queue.run_once(
        send_escalation_reminder,
        when=timedelta(minutes=30),
        name=f"esc-{chat_id}-{day_key}-{slot}",
        data={
            "day_key": day_key,
            "slot": slot,
            "chat_id": chat_id,
        },
    )


async def dispatch_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = CONFIG.tz_aware_now
    current_slot = now.strftime("%H:%M")
    day_key = now.strftime("%Y-%m-%d")
    timestamp = now.isoformat()

    for chat_id in SUBSCRIBERS.get_all():
        slots = get_user_slots(chat_id)
        if current_slot not in slots:
            continue

        existing = STORAGE.list_day(make_day_key(chat_id, day_key))
        if any(item.slot == current_slot for item in existing):
            continue

        await send_reminder_to_chat(context, chat_id, current_slot, day_key, timestamp)


async def send_reminder_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    slot: str,
    day_key: str,
    timestamp: str,
) -> None:
    STORAGE.mark_sent(make_day_key(chat_id, day_key), slot, timestamp)
    period = get_period_name(slot)
    morning_texts = [
        "💕 Доброе утро, Лизочка!\n\nНе забудь принять таблеточку Анаприлина, солнышко. Это важно для твоего здоровья! 💊",
        "☀️ Привет, моя хорошая!\n\nВремя выпить утреннюю таблетку Анаприлина. Я забочусь о тебе! 💊💕",
    ]
    afternoon_texts = [
        "🌸 Лизонька, привет!\n\nПора принять дневную таблетку Анаприлина. Не забудь, пожалуйста! 💊",
        "💐 Как дела, солнышко?\n\nНапоминаю про дневную таблеточку Анаприлина. Береги себя! 💊💕",
    ]
    evening_texts = [
        "🌙 Добрый вечер, Лизочка!\n\nПора принять вечернюю таблетку Анаприлина. Я рядом! 💊",
        "✨ Милая, не забудь вечернюю таблеточку Анаприлина. Это важно! 💊💕",
    ]
    text = random.choice(morning_texts if period == "утром" else afternoon_texts if period == "днем" else evening_texts)

    try:
        image_path = get_random_image()
        if image_path:
            message = await send_photo_with_retry(
                context.bot, chat_id, image_path, text,
                reply_markup=build_keyboard(day_key, slot, chat_id),
            )
        else:
            message = await send_with_retry(
                context.bot, chat_id, text,
                reply_markup=build_keyboard(day_key, slot, chat_id),
            )
        if message:
            REMINDER_MESSAGES.add_message(chat_id, day_key, slot, message.message_id)
            schedule_nag_and_escalation(context, chat_id, day_key, slot)
            logger.info(f"Напоминание {slot} успешно отправлено для chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания {slot} для chat_id={chat_id}: {e}")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    # Deprecated path (оставлено для совместимости старых job-данных)
    data = context.job.data if context.job else {}
    slot = data.get("slot")
    chat_id = data.get("chat_id")
    if slot is None or chat_id is None:
        return
    now = CONFIG.tz_aware_now
    await send_reminder_to_chat(context, chat_id, slot, now.strftime("%Y-%m-%d"), now.isoformat())


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
    
    try:
        message = await send_with_retry(
            context.bot, chat_id, text,
            reply_markup=build_keyboard(day_key, slot, chat_id),
        )
        
        if message:
            # Сохраняем message_id для последующего удаления
            REMINDER_MESSAGES.add_message(chat_id, day_key, slot, message.message_id)
            logger.info(f"Повторное напоминание {slot} #{nag_count} отправлено для chat_id={chat_id}")
        else:
            logger.error(f"Не удалось отправить повторное напоминание {slot} для chat_id={chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке повторного напоминания {slot} для chat_id={chat_id}: {e}")

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


def cancel_escalation_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int, day_key: str, slot: str) -> None:
    job_queue = context.job_queue
    if job_queue is None:
        return
    job_name = f"esc-{chat_id}-{day_key}-{slot}"
    for job in [job for job in job_queue.jobs() if job.name == job_name]:
        job.schedule_removal()


def cancel_all_followups_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Отменяет все nag/escalation задачи для чата (после смены расписания)."""
    job_queue = context.job_queue
    if job_queue is None:
        return
    prefixes = (f"nag-{chat_id}-", f"esc-{chat_id}-")
    for job in job_queue.jobs():
        name = job.name or ""
        if name.startswith(prefixes):
            job.schedule_removal()


async def send_escalation_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    day_key = data["day_key"]
    slot = data["slot"]
    chat_id = data["chat_id"]

    statuses = STORAGE.list_day(make_day_key(chat_id, day_key))
    slot_status = next((item for item in statuses if item.slot == slot), None)
    if not slot_status or slot_status.status != "pending":
        return

    alert_text = "Лиза не подтвердила таблетку, напомни ей!"
    try:
        await context.bot.send_message(chat_id=ESCALATION_TARGET, text=alert_text)
        logger.info("Эскалация отправлена для chat_id=%s slot=%s -> %s", chat_id, slot, ESCALATION_TARGET)
    except Exception as e:
        logger.warning("Не удалось отправить эскалацию: %s", e)


async def delete_reminder_messages(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    day_key: str,
    slot: str,
    except_message_id: int | None = None,
    keep_root_message: bool = False,
) -> str | None:
    """Удаляет дубликаты напоминаний и возвращает file_id картинки (если есть)."""
    message_ids = REMINDER_MESSAGES.get_messages(chat_id, day_key, slot)
    keep_ids = set()

    if except_message_id is not None:
        keep_ids.add(except_message_id)

    # Первый message_id — исходное (корневое) напоминание; его можно сохранить
    if keep_root_message and message_ids:
        keep_ids.add(message_ids[0])

    message_ids_to_delete = [msg_id for msg_id in message_ids if msg_id not in keep_ids]

    for msg_id in message_ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.debug(f"Удалено сообщение {msg_id} для {chat_id}")
        except BadRequest as e:
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")

    return REMINDER_MESSAGES.remove_messages(chat_id, day_key, slot, message_ids_to_delete)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data is None:
        await query.answer("Ошибка обработки запроса.")
        return
    
    # Кнопки быстрого меню из /start
    if query.data.startswith("menu_"):
        chat_id = query.message.chat_id if query.message else None
        if chat_id is None:
            await query.answer("Ошибка получения чата.")
            return
        await query.answer()
        if query.data == "menu_main":
            await send_with_retry(
                context.bot,
                chat_id,
                "🏠 Главное меню",
                reply_markup=build_start_menu_keyboard(),
            )
            return
        if query.data == "menu_status":
            await send_status(context, chat_id)
        elif query.data == "menu_calendar":
            await send_calendar(context, chat_id)
        elif query.data == "menu_test":
            await send_test_reminder(context, chat_id, is_admin_test=False)
        elif query.data == "menu_stop":
            if SUBSCRIBERS.contains(chat_id):
                SUBSCRIBERS.remove(chat_id)
                await send_with_retry(
                    context.bot, chat_id,
                    "😢 Хорошо, Лизочка, я перестану напоминать...\n"
                    "Если передумаешь, нажми /start 💕",
                    reply_markup=build_back_to_menu_keyboard(),
                )
            else:
                await send_with_retry(
                    context.bot,
                    chat_id,
                    "Ты уже не подписана на напоминания.",
                    reply_markup=build_back_to_menu_keyboard(),
                )
        elif query.data == "menu_reschedule_help":
            await begin_reschedule_flow(context, chat_id)
        return

    if query.data in {"reschedule_restart", "reschedule_save"}:
        chat_id = query.message.chat_id if query.message else None
        if chat_id is None:
            await query.answer("Ошибка получения чата.")
            return
        await query.answer()
        if query.data == "reschedule_restart":
            await begin_reschedule_flow(context, chat_id)
            return
        values = context.user_data.get("reschedule_values", {})
        error = validate_reschedule_values(values) if isinstance(values, dict) else "Данных нет."
        if error:
            await send_with_retry(
                context.bot,
                chat_id,
                f"⚠️ Нельзя сохранить: {error}",
                reply_markup=build_reschedule_confirm_keyboard(),
            )
            return
        slots = [values["morning"], values["afternoon"], values["evening"]]
        USER_SETTINGS.set_times(chat_id, slots)
        cancel_all_followups_for_chat(context, chat_id)
        context.user_data.pop("reschedule_step", None)
        context.user_data.pop("reschedule_values", None)
        await send_with_retry(
            context.bot,
            chat_id,
            "✅ Расписание сохранено:\n" + ", ".join(slots),
            reply_markup=build_back_to_menu_keyboard(),
        )
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
        
        # Удаляем все повторные напоминания (nag), но сохраняем корневое сообщение с фото
        await delete_reminder_messages(
            context,
            chat_id,
            day_key,
            slot,
            except_message_id=current_message_id,
            keep_root_message=True,
        )
        
        confirm_text = random.choice(confirm_texts)
        
        # Редактируем текущее сообщение (сохраняем картинку, меняем подпись)
        try:
            if query.message.photo:
                # Если это сообщение с фото — редактируем подпись
                await query.edit_message_caption(caption=confirm_text, reply_markup=None)
            else:
                # Если это текстовое сообщение — редактируем текст
                await query.edit_message_text(text=confirm_text, reply_markup=None)
        except BadRequest as e:
            logger.debug(f"Не удалось отредактировать сообщение: {e}")
            # Fallback: отправляем новое сообщение
            await context.bot.send_message(chat_id=chat_id, text=confirm_text)
        
        # Отменяем все запланированные напоминания для этого слота
        cancel_nag_reminders(context, chat_id, day_key, slot)
        cancel_escalation_reminder(context, chat_id, day_key, slot)
    elif action == "skip":
        STORAGE.mark_skipped(chat_day_key, slot, CONFIG.tz_aware_now.isoformat())
        
        # Удаляем все повторные напоминания (nag), но сохраняем корневое сообщение с фото
        await delete_reminder_messages(
            context,
            chat_id,
            day_key,
            slot,
            except_message_id=current_message_id,
            keep_root_message=True,
        )
        
        skip_text = (
            "😔 Лизочка, ты пропустила таблетку...\n\n"
            "Пожалуйста, постарайся не забывать! Это важно для твоего здоровья. ❤️"
        )
        
        # Редактируем текущее сообщение (сохраняем картинку, меняем подпись)
        try:
            if query.message.photo:
                # Если это сообщение с фото — редактируем подпись
                await query.edit_message_caption(caption=skip_text, reply_markup=None)
            else:
                # Если это текстовое сообщение — редактируем текст
                await query.edit_message_text(text=skip_text, reply_markup=None)
        except BadRequest as e:
            logger.debug(f"Не удалось отредактировать сообщение: {e}")
            # Fallback: отправляем новое сообщение
            await context.bot.send_message(chat_id=chat_id, text=skip_text)
        
        # Отменяем все запланированные напоминания для этого слота
        cancel_nag_reminders(context, chat_id, day_key, slot)
        cancel_escalation_reminder(context, chat_id, day_key, slot)
    else:
        await query.edit_message_text("Что-то пошло не так... 🤔")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    handled = await handle_reschedule_text(update, context)
    if handled:
        return


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
        "/aclear_day — инфо об очистке данных"
    )


async def admin_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет тестовое напоминание с картинкой."""
    if not is_admin(update):
        await update.message.reply_text("❌ У тебя нет доступа к админским командам.")
        return
    
    chat = update.effective_chat
    await send_test_reminder(context, chat.id, is_admin_test=True)
    await update.message.reply_text("✅ Тестовое напоминание отправлено!")


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


def build_application() -> Application:
    # Увеличенные таймауты для российского сервера (проблемы с доступом к Telegram API)
    proxy = (os.environ.get("TELEGRAM_PROXY") or "").strip() or None
    if proxy:
        logger.info("Telegram API через прокси (TELEGRAM_PROXY задан).")
        # Через SOCKS TLS к api.telegram.org часто дольше; 5 с даёт ложные ConnectTimeout
        req_connect, gu_connect = 25.0, 25.0
    else:
        req_connect, gu_connect = 10.0, 5.0

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=req_connect,
        read_timeout=15.0,
        write_timeout=15.0,
        pool_timeout=5.0,
        proxy=proxy,
    )

    # Для long polling нужен большой таймаут - это нормально
    get_updates_request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=gu_connect,
        read_timeout=60.0,  # Long polling ждёт до 60 сек - это ок
        write_timeout=5.0,
        pool_timeout=3.0,
        proxy=proxy,
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
    app.add_handler(CommandHandler("reschedule", reschedule))
    app.add_handler(CommandHandler("reshedule", reschedule))
    
    # Админские команды
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("atest", admin_test_reminder))
    app.add_handler(CommandHandler("atest_nag", admin_test_nag))
    app.add_handler(CommandHandler("astatus", admin_status))
    app.add_handler(CommandHandler("asubs", admin_subscribers))
    app.add_handler(CommandHandler("abroadcast", admin_broadcast))
    app.add_handler(CommandHandler("aclear_day", admin_clear_day))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    app.job_queue.run_repeating(
        dispatch_reminders,
        interval=timedelta(minutes=1),
        first=2,
        name="reminder-dispatcher",
    )
    return app


def main() -> None:
    logger.info("Запуск бота. Базовые времена (по умолчанию): %s", ", ".join(t.strftime("%H:%M") for t in CONFIG.reminder_times))
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

