from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, UserSettings
from app.security import TelegramAuthError, validate_telegram_init_data


def current_user(
    x_telegram_init_data: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if settings.auth_mode == "telegram":
        try:
            identity = validate_telegram_init_data(
                x_telegram_init_data or "",
                settings.telegram_bot_token.get_secret_value(),
                settings.telegram_initdata_max_age_seconds,
            )
        except TelegramAuthError as exc:
            raise HTTPException(
                status_code=401, detail="Invalid Telegram authentication"
            ) from exc
    else:
        identity = {"id": 100000001, "first_name": "Local Learner"}
    user = db.scalar(select(User).where(User.telegram_id == identity["id"]))
    if not user:
        user = User(
            telegram_id=identity["id"],
            first_name=identity["first_name"],
            settings=UserSettings(
                ui_language="ru", target_language="en", daily_goal=10
            ),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.settings is None:
        user.settings = UserSettings(
            ui_language="ru", target_language="en", daily_goal=10
        )
        db.commit()
        db.refresh(user)
    return user
