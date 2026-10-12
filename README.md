# Lingvéra

Lingvéra — Telegram-first приложение для коротких уроков английского с русским интерфейсом. В репозитории есть FastAPI backend, SQLAlchemy/PostgreSQL, миграции Alembic, React + TypeScript Mini App и необязательный aiogram бот.

Это проверяемый MVP, не production-релиз. В локальном курсе A1 30 уроков и 120 упражнений трёх типов; backend хранит курсы, уроки и упражнения в PostgreSQL/SQLite, проверяет ответы и сохраняет попытки и прогресс. Для слов есть backend-планировщик с Again/Hard/Good/Easy; это прозрачная MVP-эвристика, не полный SM-2. Напоминания, платежи, AI и админка пока отсутствуют.

## Требования

- Python 3.12
- Node.js 20+ и npm
- Docker Desktop для PostgreSQL-варианта (не обязателен для SQLite)
- PowerShell 7 или Windows PowerShell

## Вариант A — PostgreSQL в Docker Compose

Из корня репозитория в PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose поднимает PostgreSQL, backend и Vite Mini App. Backend применяет Alembic-миграции и идемпотентно загружает начальный курс перед запуском API. Локальный Compose намеренно использует `AUTH_MODE=dev`; не публикуйте эти службы в интернет.

- Mini App: http://localhost:5173
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness (проверяет БД и миграции): http://localhost:8000/ready

Данные PostgreSQL сохраняются в named volume `postgres_data`. Для полного сброса volume требуется отдельное осознанное действие; проект не удаляет его при обычном запуске.

## Вариант B — разработка без Docker на SQLite

В PowerShell из корня репозитория:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
$env:APP_ENV = "development"
$env:AUTH_MODE = "dev"
$env:DATABASE_URL = "sqlite:///./lingvera.db"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.seed_content
.\.venv\Scripts\python.exe -m app.validate_content
.\.venv\Scripts\python.exe -m app.validate_content --check-db
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

Для Mini App во втором окне PowerShell:

```powershell
Set-Location frontend
npm ci
npm run dev
```

В репозитории зафиксирован `frontend/package-lock.json`; для установки используйте `npm ci`.

SQLite включён для локальной разработки и тестов. В SQLite также применяются внешние ключи. Production использует PostgreSQL; URL базы задаётся через `DATABASE_URL` и не подменяется автоматически.

После применения миграций повторно загружайте демонстрационный контент командой `python -m app.seed_content` из `backend`. Команда валидирует локальный JSON и выполняет upsert по slug, не удаляя данные.

## Учебный API

Все маршруты ниже требуют обычную авторизацию из раздела выше.

- `GET /api/v1/courses` и `GET /api/v1/courses/{slug}` — список и описание опубликованных курсов.
- `GET /api/v1/courses/{slug}/lessons` — уроки курса по порядку с признаком завершения текущим пользователем.
- `GET /api/v1/lessons/{slug}` — урок и упражнения без ключей правильных ответов.
- `POST /api/v1/lessons/{slug}/answer` — проверяет ответ и сохраняет попытку.
- `GET /api/v1/progress` и `GET /api/v1/progress/lessons` — статистика и завершённые уроки пользователя.
- `GET /api/v1/dashboard` — курс, следующий рекомендованный урок, дневная цель, активность за 7 UTC-дней, серия и раздельные lifetime-метрики.
- `GET /api/v1/review/due` — личные слова к повтору без переводов.
- `GET /api/v1/vocabulary/{id}/translation` — явное раскрытие перевода слова к повтору.
- `POST /api/v1/vocabulary/{id}/review` — оценка `again|hard|good|easy` с серверным расчётом следующей даты.

Пример запроса: `POST /api/v1/lessons/about-me/answer` с телом `{"exercise_id":"about-2","answer":["t1","t2","t3","t4"]}`. `choice` принимает ID варианта, `text` — строку, `word_order` — список token ID в порядке ответа. Проверка выполняется на сервере. Текст нормализуется по Unicode NFC, регистру и пробелам; диакритика сохраняется.

Дневная цель — число проверенных учебных действий, не минуты. Она учитывает уникальное верно решённое упражнение и принятую backend оценку повтора; неправильно отвеченные попытки не считаются. В настройках Mini App доступны цели 5/10/15 действий. Streak и неделя считаются по UTC; локальная timezone пользователя пока не хранится. Ежедневная история начинает накапливаться после применения миграции `0005_learning_activity`, без выдуманного backfill.

## Telegram Mini App и production-настройки

1. Создайте бота через BotFather и задайте публичный HTTPS URL Mini App.
2. Храните bot token только в переменной окружения `TELEGRAM_BOT_TOKEN`; не добавляйте его в frontend или Git.
3. Укажите `APP_ENV=production`, `AUTH_MODE=telegram`, `MINI_APP_URL=https://ваш-домен` и PostgreSQL URL.
4. В BotFather настройте домен/кнопку Mini App. Клиент отправляет необработанный `Telegram.WebApp.initData` в `X-Telegram-Init-Data`; backend проверяет HMAC и `auth_date` при каждом защищённом запросе.
5. Production-конфигурация отклоняет dev-личность, пустой token и URL без HTTPS.

Обычный `docker-compose.yml` предназначен только для локальной разработки: он явно задаёт dev-авторизацию и не является production deployment-конфигурацией. Нужны внешний HTTPS reverse proxy, secret store, firewall, резервное копирование, мониторинг и проверенная инфраструктура.

## Тесты и проверки

Backend из каталога `backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app migrations tests
.\.venv\Scripts\alembic.exe upgrade head
```

Frontend из каталога `frontend`:

```powershell
npm ci
npm run typecheck
npm run build
```

Migration проверяйте на целевой тестовой БД. Не запускайте команды сброса на БД с пользовательскими данными. Начальная миграция совместима с чистой базой и аккуратно помечает уже созданные текущим MVP таблицы без удаления строк.

## Структура

- `backend/app` — конфигурация, безопасность, ORM-модели, API, сервис проверки учебных ответов, валидатор контента и бот.
- `backend/content/en_ru_a1.json` — курс A1 на 30 уроков/120 упражнений с тематической лексикой и двумя уровнями подсказок; `python -m app.validate_content` проверяет локальную схему, `python -m app.validate_content --check-db` сверяет загруженные связи.
- `backend/migrations` — Alembic, включая `0003_vocabulary_review_state`, `0004_lesson_vocabulary`, `0005_learning_activity` и `0006_exercise_hints`.
- `backend/tests` — проверки безопасности, API, контента и миграций.
- `frontend/src` — Mini App на React/TypeScript.
- `docs` — архитектура, API, модель данных, безопасность и приёмка.

## Текущее состояние и ограничения

Приложение сохраняет пользователей, настройки, курс, уроки, попытки и завершения уроков в БД. Пользователь при `AUTH_MODE=dev` — одна локальная тестовая личность, доступная только в `APP_ENV=development`. В Telegram-режиме доверие основано только на валидном Telegram initData.

Не проверены production-развёртывание, реальный Telegram bot, PostgreSQL-соединение в этой среде, webhook и резервное восстановление. Compose конфигурация подготовлена, но Docker должен быть установлен и запущен на машине владельца.

В среде проверки Docker CLI отсутствует, поэтому PostgreSQL Compose не запускался. Обычная Vite production-сборка из каталога с кириллическим путём завершается на Windows sandbox с `EPERM: operation not permitted, realpath .../frontend/src/main.tsx`; typecheck проходит, а собранный bundle проверен только с временной runtime-обёрткой Node, без изменений исходников для обхода ограничения. Проверка dev-сервера в этой sandbox также ограничена ошибкой realpath/dep-scan. На обычной Windows-среде без sandbox команды `npm run build` и `npm run dev` следует повторить.
