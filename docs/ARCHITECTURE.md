# Архитектура Lingvéra

Lingvéra — небольшой модульный монолит: FastAPI backend владеет идентификацией, курсами, проверкой ответов и сохранением результатов; React Mini App отображает API; необязательный aiogram бот открывает Mini App.

## Компоненты

- `backend/app/config.py` — env-конфигурация и запрет production с dev auth.
- `backend/app/security.py` — серверная проверка Telegram Web Apps `initData`.
- `backend/app/db.py`, `models.py` — SQLAlchemy 2 и модели пользователя, контента, попыток, прогресса и словаря.
- `backend/app/main.py` — HTTP API, CORS, liveness/readiness и профильные/учебные маршруты.
- `backend/app/learning.py` — серверная проверка трёх типов ответов и изоляция прогресса по пользователю.
- `backend/app/vocabulary_review.py` — личный словарь, due-выборка и детерминированное серверное интервальное расписание.
- `backend/app/content_schemas.py`, `backend/app/seed_content.py` — валидация и повторяемая загрузка контента.
- `backend/app/content_quality.py`, `backend/app/validate_content.py` — проверка связей контента с уже заполненной БД и локальный CLI-валидатор.
- `backend/content/en_ru_a1.json` — локальный курс A1: 30 уроков, 120 упражнений и тематические списки слов.
- `backend/migrations` — Alembic; startup не создаёт схему через `create_all`.
- `frontend` — React + TypeScript + Vite Mini App.
- `backend/app/bot.py` — polling `/start` и переход в Mini App.

## Данные и хранилище

PostgreSQL — целевая БД развёртывания. SQLite поддерживается для локальной разработки и автоматических тестов. `DATABASE_URL` задаёт используемый dialect; production не переключается автоматически на SQLite. Таблицы меняются миграциями; Compose применяет `alembic upgrade head` до старта API.

## Авторизация

В Telegram-режиме API принимает исходный `Telegram.WebApp.initData` через `X-Telegram-Init-Data`, проверяет подпись и срок до 1 часа и извлекает Telegram ID только из подписанного `user`. Дев-личность доступна только при `APP_ENV=development`; настройки запрещают этот режим вне development и требуют Telegram token и HTTPS Mini App URL для production.

## Ограничения MVP

Урок завершается после правильного ответа на каждое доступное упражнение; журнал хранит все попытки, а прогресс — однократное завершение. Повторы слов работают по простой MVP-эвристике, не полному SM-2. Нет напоминаний, платежей, AI, CMS, UI E2E и production deployment automation.
