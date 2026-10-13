# Lingvéra — Production Operations Checklist

This runbook distinguishes checks confirmed so far from checks that still require a real Telegram session or Render dashboard access. Do not mark a manual test complete without recording its actual result.

## Deployment facts confirmed

- Telegram bot: https://t.me/LingveraLearnBot
- Mini App: https://lingv-ra.pages.dev/
- API health endpoint: https://lingv-ra.onrender.com/health
- API readiness endpoint: https://lingv-ra.onrender.com/ready
- Render deployment runs database migrations, idempotent content seeding, starts the Telegram polling process, and runs Uvicorn.
- The owner confirmed that `/start` responds and the Mini App opens.
- The reported Render logs showed migrations and seeding completed, Uvicorn started, and `/health` returned HTTP 200.

## Manual acceptance tests still required

### 1. Progress persistence across sessions

1. Open the Mini App from Telegram.
2. Complete one exercise and wait for the result.
3. Close the Mini App fully, then reopen it from the bot.
4. Confirm the lesson completion/progress and dashboard reflect the saved result.
5. Repeat after a normal browser/Telegram restart if possible.

**Pass condition:** the same Telegram account sees the saved server-side progress after reopening. Do not use only a page refresh as the sole test.

### 2. New Telegram account and user isolation

1. Open the bot from a second Telegram account.
2. Send `/start` and open the Mini App.
3. Confirm the new account can load its own profile and lessons.
4. Complete a different exercise and change a non-sensitive setting.
5. Switch back to the first account and confirm the second account's progress/settings are not visible there.

**Pass condition:** each account has a distinct identity and isolated progress. Never share bot tokens, initData, or database credentials while collecting test results.

### 3. Render restart and recovery

1. In the Render dashboard, trigger a normal manual deploy/restart for the existing service. Do not change environment variables or delete the database.
2. Follow logs through migrations, seeding, bot startup, and API startup.
3. Check `/health` and `/ready`.
4. Send `/start` to the bot and open the Mini App again.
5. Confirm the previously saved progress is still present.

**Pass condition:** API and bot both recover and existing user data remains intact. A successful API health check alone does not prove the background bot process is alive. If the bot fails while the API remains healthy, inspect the bot's startup/error logs and consider process supervision or separating it into a dedicated worker.

### 4. Error handling

- Test an offline/slow connection and confirm the UI gives a recoverable error instead of silently losing a submitted answer.
- Check Render logs for 5xx responses, database connection errors, Telegram polling conflicts, and authorization failures.
- Treat 401 responses in production as an auth/session problem to diagnose; do not weaken `AUTH_MODE=telegram` to make the Mini App load.
- Verify invalid exercise submissions do not create false successful progress.

## Feedback, analytics, and privacy

No third-party analytics provider is assumed to be configured. Before adding one, choose the minimum events needed and document what is collected. Recommended initial events are aggregate counts for app open, lesson opened, exercise answered, lesson completed, and vocabulary review submitted. Avoid collecting raw Telegram initData, bot tokens, names, message contents, or answer text in analytics. Prefer aggregate counters or pseudonymous internal user IDs, restrict log access, and add a clear privacy notice before inviting external users.

For feedback, start with a visible contact/feedback link to the project owner or a dedicated GitHub issue template. Do not collect private user data in public GitHub issues. A future in-app feedback endpoint should validate input, rate-limit submissions, avoid logging sensitive payloads, and have an explicit retention policy.

## Database backup and restore

1. Identify the actual PostgreSQL provider used by the production `DATABASE_URL` in the hosting dashboard. Never paste the URL or credentials into an issue, chat, or repository.
2. Check the provider's available backup/export options and retention for the current plan; do not assume automatic backups exist.
3. Before real users depend on the app, create a manual database export using the provider's documented method or `pg_dump` from a trusted machine with a secure connection.
4. Store the backup outside the application container and Git repository, with access restricted. Never commit dumps or secrets.
5. Perform a restore test into a separate disposable database, then verify migrations, user rows, progress, lesson attempts, and vocabulary review state.
6. Record backup date, retention, restore steps, and owner. Repeat on a schedule appropriate to data loss tolerance.

**Important:** do not delete the Render service, PostgreSQL database, or persistent volumes as a way to test recovery. Do not run destructive reset commands against production.

## Release record

Record each manual test with date, tester, result (Pass/Fail/Blocked), and a short sanitized note. Until the persistence, second-account, restart, and restore checks are actually run, keep them marked as pending.
