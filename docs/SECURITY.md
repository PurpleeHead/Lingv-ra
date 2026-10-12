# Безопасность Lingvéra

- Mini App отправляет raw `Telegram.WebApp.initData`; backend проверяет HMAC-SHA-256 по алгоритму Telegram, отклоняет повторные поля/неверную подпись/повреждённого пользователя и проверяет `auth_date` (максимум 1 час).
- Telegram ID извлекается только из проверенного `user`. Клиентский ID не принимается как идентичность.
- Dev identity разрешена только в паре `APP_ENV=development`, `AUTH_MODE=dev`. Production требует `AUTH_MODE=telegram`, bot token и HTTPS URL Mini App.
- Bot token находится только в backend env, не передаётся frontend и не включается в ответы.
- CORS ограничен origin `MINI_APP_URL`; credentials отключены.
- ORM использует параметризованные запросы; SQLite включает foreign keys. Таблицы обслуживаются Alembic, автоматического `create_all` при старте нет.
- Ошибки авторизации сведены к 401. Readiness не раскрывает DSN и выдаёт общее 503.
- Повторные маршруты всегда фильтруют слова по проверенному `user.id`. Due-ответ не содержит перевода; отдельный reveal endpoint фиксирует действие, а rating endpoint требует этот флаг и атомарно обновляет расписание.

## До публичного релиза

Нужны HTTPS, secret store и ротация bot token, rate limiting, логи без initData/PII, резервирование и проверенное восстановление. Реальная Telegram интеграция и production PostgreSQL не проверялись в этой среде. Compose использует локальные известные credentials и не должен быть открыт в интернет.
