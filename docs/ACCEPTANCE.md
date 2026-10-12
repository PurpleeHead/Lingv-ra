# Приёмка Lingvéra

Отмечать только то, что проверено после текущих изменений.

- [x] Чистая SQLite база получает схему только через Alembic.
- [x] Миграция сохраняет строки при переходе от таблиц, созданных прежним MVP.
- [ ] PostgreSQL Compose поднимает БД и API после миграций.
- [x] `/health` и `/ready` отражают liveness и доступность мигрированной БД.
- [x] `/api/v1/me` работает только с dev identity локально или проверенным Telegram initData.
- [x] Production блокирует dev auth, отсутствующий token и HTTP Mini App URL.
- [x] Невалидный, просроченный initData и дубликаты параметров отклоняются без ослабления подписи.
- [x] Настройки сохраняются, `null` и неверные значения отвергаются.
- [x] Уроки доступны, ответы оцениваются сервером и сохраняются под нужным пользователем.
- [x] A1 содержит 30 упорядоченных уроков/120 упражнений; все исходные 15 lesson slug и 42 exercise slug сохранены, по 4 упражнения на урок, контент валидируется, повторный seed не создаёт дубликатов.
- [x] Тематические слова появляются в личном словаре после завершения урока; повторный seed/запрос не дублирует слова и не сбрасывает расписание.
- [x] Миграция 0004 добавляет уроковую лексику и уникальный персональный source key без удаления пользовательских строк.
- [x] Три типа упражнений (choice, text, word_order) проверяются backend, правильные ответы скрыты до ответа.
- [x] Успешные/ошибочные попытки изолированы по пользователю и учитываются в прогрессе.
- [x] Завершение урока сохраняется максимум одной записью на пользователя и урок даже при повторном ответе.
- [x] Повторное применение Alembic не портит данные; переход от схемы 0001 сохраняет существующего пользователя и настройки.
- [x] Frontend TypeScript typecheck проходит; production bundle собран с временной runtime-обёрткой Node.
- [ ] Обычная `npm run build` и визуальная проверка адаптивности в Windows-среде без sandbox.
- [ ] Docker Compose и настоящий Telegram bot проверены на машине с Docker и bot token.
- [x] Слова к повтору фильтруются по due-времени, выдаются без перевода и ограничены владельцем.
- [x] Перевод раскрывается отдельным действием; backend не принимает rating до reveal.
- [x] Again/Hard/Good/Easy дают детерминированные интервалы и обновляют персональные счётчики.
- [x] Повторные оценки до нового due срока не дублируют результат; неизвестные/чужие слова недоступны.
- [x] Миграция 0003 сохраняет существующие слова и переводит расписание к безопасному исходному состоянию.
- [ ] Review flow визуально проверен в Telegram Mini App и на узком мобильном экране.

SRS реализован как MVP-эвристика, а не полный SM-2; завершение уроков/score, уведомления, оплата, AI и production deploy пока отсутствуют.

## Stage 6 — dashboard, дневная цель и аналитика

- [x] `/api/v1/dashboard` защищён авторизацией и не принимает метрики от клиента.
- [x] Верный ответ добавляет идемпотентную дневную activity запись; неправильный — нет.
- [x] Сводка различает попытки, правильные отправки, уникальные упражнения, уроки, due-слова, review submissions и уникальную лексику.
- [x] Цель хранится в настройках, проверяется backend и считается действиями, не минутами.
- [x] Серия/семидневная лента рассчитываются детерминированно в UTC, тестируются пустые дни и пропуски.
- [x] Миграция `0005_learning_activity` аддитивна и не выдумывает прошлую историю.
- [x] Frontend получает аналитику от API и сохраняет гибкий доступ к урокам.
- [ ] Обычная Vite production-сборка/визуальная проверка в Windows вне sandbox и Telegram Mini App.
- [ ] PostgreSQL Compose, настоящий Telegram и production deploy требуют Docker, token, домена и окружения владельца.

## Stage 7 — A1 curriculum and content quality

- [x] Source contains 30 lessons/120 exercises across all supported exercise types.
- [x] Original 15 lesson slugs and 42 exercise slugs remain present; each lesson now has four exercises.
- [x] New vocabulary is added to the correct user only after lesson completion.
- [x] Repeated seed preserves user data and does not delete records.
- [x] Content validation checks non-empty localized fields, unique IDs/options, valid answer references, duplicate exercise prompts, and seeded DB relationships.
- [x] Word-order tokens are not exposed in answer order; backend still validates exact token sequence.
- [ ] PostgreSQL and visual browser/Telegram validation require external runtime availability.

## Stage 8 — two-level exercise hints

- [x] All 120 authored exercises have non-empty Russian and English hints at levels 1 and 2.
- [x] Hints are stored separately from public prompt/options and answer keys, and delivered through an authenticated level-specific API.
- [x] API validates hint level and that the exercise belongs to the requested published/available lesson.
- [x] Mini App requests hints on explicit learner action, exposes level 2 only after level 1, and clears hints when moving to another exercise.
- [x] Tests cover auth, localized delivery, hidden-by-default exercise response, level validation, and resource scope.
- [ ] Mobile visual review in browser/Telegram remains pending; normal Vite build is blocked by Windows sandbox `EPERM` resolving the Cyrillic project path.

## Stage 8 follow-up — content audit and API reliability

- [x] Audit report covers all 30 lessons/120 exercises, 240 hint levels and 480 bilingual hint strings; the report separates mechanical validation from teacher-level editorial review.
- [x] Russian text in 36 English instruction/explanation pairs is corrected; the shopping-quantity prompt/distractors and `Japanish` distractor are improved without changing slug or option IDs.
- [x] Full-answer leaks found in five hints are removed; deterministic content validation now rejects complete answer leakage and broad hint reuse.
- [x] Seeded DB validator compares course, lesson, exercise, hint, and answer fields against the authored source.
- [x] Exact previous routine hint URL returns HTTP 200 from the current local API; local DB is at migration head and seeded.
- [x] Hint-request integration test confirms no learning events, completions, vocabulary, activities, or dashboard-stat changes; subsequent wrong and correct answers still grade normally.
- [x] Sample SQLite URL and README setup are aligned to `lingvera.db`; repeated seed preserved every user-data row count.
- [ ] Real browser/Telegram WebView visual check, Docker/PostgreSQL and qualified teacher review remain external/manual checks.
