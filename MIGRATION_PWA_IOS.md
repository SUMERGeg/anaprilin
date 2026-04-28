# План переезда: Telegram-бот -> iPhone PWA (offline-first)

## 1) Цель переезда

Перенести текущий проект напоминаний о приёме Анаприлина из Telegram-бота в формат мини-приложения (PWA),
которое запускается с экрана iPhone, работает офлайн для основных сценариев и синхронизируется с сервером при
появлении интернета.

Проект рассчитан на постоянное использование 1-2 пользователями.

## 1.1) Где брать референс (абсолютные пути + официальные ссылки)

### Локальные референсы текущего проекта (источник логики)

1. Главный файл Telegram-бота: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py`
- Парсинг расписания: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:56`
- Конфиг и timezone: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:72`
- Пользовательские слоты: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:119`
- Календарная агрегация: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:328`
- Планирование nag/escalation: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:639`
- Диспетчер слотов: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:665`
- Повторные напоминания: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:737`
- Обработка confirm/skip: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:882`
- Сетевые таймауты/прокси/app wiring: `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:1224`

2. Файл хранилищ (основа для domain/data слоя): `C:\Users\User\Desktop\Desk\Anaprilin\storage.py`
- История приёмов: `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:18`
- Временное хранилище message/photo id: `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:132`
- Пользовательские настройки расписания: `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:198`
- Подписчики: `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:238`

3. Конфиги и переменные окружения:
- `C:\Users\User\Desktop\Desk\Anaprilin\env.example`
- `C:\Users\User\Desktop\Desk\Anaprilin\requirements.txt`

4. Текущая документация запуска/деплоя:
- `C:\Users\User\Desktop\Desk\Anaprilin\README.md`

### Внешние официальные референсы (куда смотреть при разработке)

1. iOS Home Screen Web Apps / Web Push / Service Worker:
- WebKit (Web Push on iOS/iPadOS): [https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)
- WebKit (Service Workers): [https://webkit.org/blog/8090/workers-at-your-service/](https://webkit.org/blog/8090/workers-at-your-service/)
- Apple docs (web push): [https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers)

2. PWA/offline паттерны:
- MDN Offline and background operation: [https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation)
- Workbox docs: [https://developer.chrome.com/docs/workbox/](https://developer.chrome.com/docs/workbox/)

3. Backend/API стек:
- FastAPI docs: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
- SQLModel docs: [https://sqlmodel.tiangolo.com/](https://sqlmodel.tiangolo.com/)
- APScheduler docs: [https://apscheduler.readthedocs.io/en/stable/](https://apscheduler.readthedocs.io/en/stable/)

4. Web Push серверная реализация:
- pywebpush: [https://github.com/web-push-libs/pywebpush](https://github.com/web-push-libs/pywebpush)
- web.dev Web Push protocol overview: [https://web.dev/push-notifications-web-push-protocol/](https://web.dev/push-notifications-web-push-protocol/)

---

## 2) Ключевые ограничения iOS/PWA (важно принять заранее)

1. Офлайн-режим на iPhone возможен через Service Worker + кэш + IndexedDB, но только после первого онлайнового запуска.
2. Push-уведомления в iOS для web app доступны только для приложений, добавленных на Home Screen, и iOS 16.4+.
3. Если устройство полностью офлайн, серверные push-напоминания не придут до восстановления сети.
4. Safari/iOS может очищать веб-данные при нехватке памяти/долгом неиспользовании приложения.
5. Надёжных фоновых периодических задач как у нативных iOS-приложений у PWA нет.

Вывод: делаем `offline-first интерфейс и запись отметок`, но `уведомления 24/7` остаются сеть-зависимыми.

---

## 3) Целевая архитектура

## 3.1 High-level схема

1. `PWA клиент (iPhone)`
- UI напоминаний, статуса, календаря.
- Локальная база (IndexedDB) для офлайн-данных.
- Service Worker для кэша shell/статики/API-стратегий.
- Подписка на Web Push (при согласии пользователя).

2. `Backend API (Python/FastAPI)`
- REST API для расписания, событий приёма, статуса.
- Планировщик серверных напоминаний.
- Отправка Web Push.
- Синхронизация и разрешение конфликтов.

3. `DB`
- Для 1-2 пользователей достаточно SQLite (WAL) на старте.
- Опционально миграция на Postgres без изменения API-контрактов.

4. `Push сервис`
- Web Push (VAPID) через `pywebpush`.
- Хранение подписок устройств.

## 3.2 Разделение слоёв

1. `Domain/Core` (общая бизнес-логика)
- правила слотов (утро/день/вечер), статусы (pending/confirmed/skipped), эскалации.
- независим от UI, Telegram, PWA.

2. `Transport`
- раньше: Telegram handlers.
- теперь: HTTP API + Web Push события.

3. `Storage`
- сервер: SQL (SQLite/Postgres).
- клиент: IndexedDB.

---

## 4) Рекомендуемый технологический стек

## 4.1 Frontend (PWA)

1. `React + TypeScript + Vite`
- быстрый старт, хороший DX, простая сборка.

2. `TanStack Query`
- кэш API и удобная офлайн/онлайн синхронизация состояния.

3. `IndexedDB + Dexie`
- надёжное локальное хранилище для событий приёма, расписания, очереди sync.

4. `Workbox`
- готовые стратегии кэширования и управление service worker.

5. `Zod`
- валидация контрактов API на клиенте.

6. `date-fns + date-fns-tz`
- работа с локальным временем `Europe/Moscow`.

## 4.2 Backend

1. `FastAPI`
- быстрый REST API, типизация, простая интеграция с Python-логикой проекта.

2. `SQLModel` (или SQLAlchemy + Pydantic)
- модели БД + миграции через Alembic.

3. `APScheduler`
- серверные напоминания и эскалации (аналог job queue в Telegram-боте).

4. `pywebpush`
- отправка push в браузерные подписки.

5. `Uvicorn/Gunicorn`
- прод запуск.

---

## 5) Функциональная декомпозиция

## 5.1 Что переносим из текущего бота 1:1

1. Слоты напоминаний (по умолчанию 3 в день).
2. Статусы: `pending`, `confirmed`, `skipped`.
3. Повторные напоминания (nag) каждые 10 минут до лимита.
4. Календарь по дням/неделям с цветовой индикацией.
5. Персональная настройка расписания.

## 5.2 Что меняется концептуально

1. `/start`, `/status`, `/calendar`, inline кнопки -> экраны и кнопки внутри PWA.
2. `chat_id` -> `user_id` + `device_id`.
3. Эскалация в Telegram -> push-эскалация/резервный канал (опционально email/SMS).
4. message_id-ориентированная логика удаления сообщений исчезает.

---

## 6) Модель данных (сервер)

## 6.1 Таблицы

1. `users`
- id, name, timezone, created_at, updated_at.

2. `devices`
- id, user_id, platform, app_version, last_seen_at.

3. `push_subscriptions`
- id, device_id, endpoint, p256dh, auth, enabled, created_at, updated_at.

4. `schedules`
- id, user_id, slots_json (`["09:00","15:00","21:00"]`), active_from.

5. `intake_events`
- id (uuid), user_id, day_key, slot, status, sent_at, acted_at, source (`server|client`), revision.

6. `reminder_jobs` (опционально, если нужен аудит)
- id, user_id, day_key, slot, job_type (`primary|nag|escalation`), run_at, state.

## 6.2 Клиентская локальная модель (IndexedDB)

1. `local_schedule`
2. `local_events`
3. `outbox` (очередь операций для синхронизации)
4. `sync_meta` (last_sync_token, last_success_at)

---

## 7) API-контракты (черновой минимальный набор)

1. `POST /auth/device-login`
- вход с коротким PIN/магической ссылкой (без тяжёлой IAM для 1-2 пользователей).

2. `GET /me/schedule`
3. `PUT /me/schedule`

4. `GET /me/events?from=YYYY-MM-DD&to=YYYY-MM-DD`
5. `POST /me/events` (confirm/skip)

6. `POST /me/push/subscribe`
7. `DELETE /me/push/subscribe/{id}`

8. `POST /sync/pull`
- отдать изменения после `cursor/revision`.

9. `POST /sync/push`
- принять офлайн-операции из outbox.

Правило конфликтов: `last-write-wins` по `revision`, но с защитой от деградации статуса (например confirmed не перетирать в pending).

---

## 8) Offline-first стратегия

## 8.1 Что должно работать без интернета

1. Запуск приложения (app shell).
2. Просмотр уже загруженного расписания.
3. Отметка «Приняла / Пропустить».
4. Просмотр локального календаря и статуса за последние дни.

## 8.2 Что не работает без интернета

1. Получение новых push.
2. Обновление данных на сервере в реальном времени.
3. Доставка напоминаний при полностью закрытом приложении и отсутствии сети.

## 8.3 Service Worker кэш-стратегии

1. `Cache First` для статических ассетов (js/css/fonts/icons).
2. `Network First + fallback cache` для API чтения (`GET`).
3. `Background queue` для `POST/PUT` (через outbox + ручной retry при online).
4. Версионирование кэша через `APP_VERSION`.

---

## 9) Уведомления и напоминания

## 9.1 Базовый механизм

1. Серверный APScheduler формирует напоминание по расписанию.
2. Backend отправляет Web Push на активные подписки устройства.
3. Тап по уведомлению открывает PWA на нужном экране (slot/day).

## 9.2 Повторные напоминания (nag)

1. Если статус слота не изменился с `pending` через 10 минут -> push #2.
2. Повторять до 6 раз или до `confirmed/skipped`.
3. При подтверждении отменять оставшиеся задачи.

## 9.3 Резервный канал (рекомендуется)

Для сценария «Telegram нестабилен» добавить резерв:
1. email через SMTP (дешево и просто), или
2. SMS-провайдер (дороже, но надёжнее как аварийный канал).

---

## 10) Безопасность

1. HTTPS only.
2. HttpOnly secure cookies или short-lived JWT + refresh.
3. Шифрование push-ключей в БД (как минимум на уровне диска/бэкапов).
4. Минимизация персональных данных (только то, что нужно для напоминаний).
5. Логи без чувствительных токенов.

---

## 11) Этапы миграции

## Этап 0. Подготовка (0.5-1 день)

1. Зафиксировать текущие требования по UX/текстам напоминаний.
2. Заморозить изменения в Telegram-боте (кроме багфиксов).
3. Утвердить целевой стек и контракты API.

## Этап 1. Вынос бизнес-логики в core-модуль (1-2 дня)

1. Извлечь из `bot.py` доменные функции:
- вычисление слотов,
- статусы,
- nag/escalation правила,
- календарную агрегацию.
2. Источник для extraction:
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:56` (`parse_times`)
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:119` (`get_user_slots`)
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:328` (`build_calendar_text_and_keyboard`)
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:639` (`schedule_nag_and_escalation`)
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:665` (`dispatch_reminders`)
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py:737` (`send_nag_reminder`)
- `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:18` (`ConfirmationStorage`)
- `C:\Users\User\Desktop\Desk\Anaprilin\storage.py:198` (`UserSettingsStorage`)
3. Сделать pure-Python модуль без Telegram-зависимостей.
4. Добавить unit-тесты на core-правила.

## Этап 2. Backend API + DB (2-4 дня)

1. Поднять FastAPI приложение.
2. Описать SQL-модели и миграции.
3. Реализовать schedule/events/sync endpoints.
4. Добавить APScheduler задачи и аудит логов.

## Этап 3. PWA клиент (3-6 дней)

1. Структура экранов:
- Главная (сегодняшние слоты),
- Календарь,
- Настройки расписания,
- Статус синхронизации.
2. IndexedDB + outbox sync.
3. Service Worker + offline shell.
4. Add-to-Home-Screen инструкция внутри приложения.

## Этап 4. Web Push (1-2 дня)

1. Генерация VAPID ключей.
2. Подписка устройства из PWA.
3. Отправка push сервером.
4. Deeplink-обработка открытия уведомления.
5. Референсы:
- [https://github.com/web-push-libs/pywebpush](https://github.com/web-push-libs/pywebpush)
- [https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers)
- [https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)

## Этап 5. Миграция данных и запуск (1 день)

1. Конвертер `data/confirmations.json` -> SQL.
2. Ручная валидация истории за последние 30 дней.
3. Soft-launch на 1 пользователе.
4. Через 3-7 дней подключение второго пользователя.

Итого: реалистично `8-16 рабочих дней` на качественный переезд.

---

## 12) Структура репозитория (целевая)

```text
anaprilin/
  backend/
    app/
      api/
      core/
      models/
      services/
      scheduler/
    alembic/
    pyproject.toml
  frontend/
    src/
      app/
      features/
      entities/
      shared/
    public/
      manifest.webmanifest
      icons/
    vite.config.ts
    package.json
  data-migration/
    import_confirmations.py
  docs/
    MIGRATION_PWA_IOS.md
```

---

## 13) Критерии готовности (Definition of Done)

1. Приложение устанавливается на iPhone через Add to Home Screen.
2. Без интернета открывается и позволяет ставить отметки по приёму.
3. При восстановлении сети офлайн-отметки синхронизируются без потерь.
4. Push-напоминания приходят в пределах SLA (например <= 60 секунд от планового времени).
5. Повторные напоминания корректно останавливаются после подтверждения.
6. Календарь и статусы совпадают между клиентом и сервером.

---

## 14) Риски и как снизить

1. Нестабильность iOS офлайн-кэша в отдельных сценариях.
- Митигация: минимальный app shell, периодический health-check кэша, простой recovery flow.

2. Пользователь не дал разрешение на push.
- Митигация: явный onboarding + резервный канал уведомлений.

3. Конфликты при офлайн-изменениях.
- Митигация: revision/versioning + детерминированные правила merge.

4. Избыточная сложность для 1-2 пользователей.
- Митигация: начинать с SQLite + простого auth + минимального UI.

---

## 15) Рекомендуемая тактика запуска

1. Сначала MVP PWA:
- только 3 слота,
- confirm/skip,
- календарь,
- push.

2. Далее улучшения:
- кастомные тексты,
- резервный канал,
- админка статистики.

3. Telegram-бот оставить как fallback на переходный период 2-4 недели.

---

## 16) Минимальный стек (если нужно быстрее и дешевле)

Если цель — максимально быстро:
1. Backend: FastAPI + SQLite + APScheduler + pywebpush.
2. Frontend: React + Vite + Dexie + Workbox (без тяжёлого UI-фреймворка).
3. Деплой: один VPS (Docker Compose: api + reverse proxy).

Это покрывает потребность 1-2 пользователей с минимальной операционной нагрузкой.

---

## 17) Карта файлов переезда (абсолютные пути)

Ниже прямой mapping, чтобы разработчик понимал, где писать новый код и откуда переносить.

1. Источник (сейчас):
- `C:\Users\User\Desktop\Desk\Anaprilin\bot.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\storage.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\data\confirmations.json`
- `C:\Users\User\Desktop\Desk\Anaprilin\data\subscribers.json`

2. Целевой backend (создать):
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\core\reminders.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\core\calendar.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\api\reminders.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\api\schedule.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\services\push_service.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\scheduler\jobs.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\app\models\*.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\backend\alembic\versions\*.py`

3. Целевой frontend PWA (создать):
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\app\main.tsx`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\features\schedule\*`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\features\calendar\*`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\features\intake\*`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\shared\offline\db.ts`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\src\shared\offline\outbox.ts`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\public\manifest.webmanifest`
- `C:\Users\User\Desktop\Desk\Anaprilin\frontend\public\sw.js` (или generated через Workbox)

4. Миграция данных (создать):
- `C:\Users\User\Desktop\Desk\Anaprilin\data-migration\import_confirmations.py`
- `C:\Users\User\Desktop\Desk\Anaprilin\data-migration\import_subscribers.py`
