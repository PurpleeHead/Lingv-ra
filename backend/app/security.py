import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    """Invalid or outdated Telegram Mini App authorization data."""


def validate_telegram_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = 3600, now: int | None = None
) -> dict[str, int | str]:
    if not init_data or not bot_token:
        raise TelegramAuthError("Missing init data or bot token")
    try:
        pairs = parse_qsl(
            init_data, keep_blank_values=True, strict_parsing=True, max_num_fields=50
        )
    except ValueError as exc:
        raise TelegramAuthError("Malformed init data") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise TelegramAuthError("Duplicate init data field")
        fields[key] = value
    received_hash = fields.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise TelegramAuthError("Missing or malformed signature")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramAuthError("Invalid signature")
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramAuthError("Invalid auth_date") from exc
    current = int(time.time()) if now is None else now
    if (
        auth_date <= 0
        or auth_date > current + 60
        or current - auth_date > max_age_seconds
    ):
        raise TelegramAuthError("Expired or invalid auth_date")
    try:
        user = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Invalid user payload") from exc
    user_id = user.get("id") if isinstance(user, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise TelegramAuthError("Missing Telegram user id")
    return {"id": user_id, "first_name": str(user.get("first_name") or "Learner")[:100]}
