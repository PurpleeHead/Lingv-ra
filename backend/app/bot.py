import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from app.config import settings

router = Router()


@router.message(CommandStart())
async def start(message: Message):
    if settings.mini_app_url.startswith("https://"):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть Lingvéra",
                        web_app=WebAppInfo(url=settings.mini_app_url),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Оставить отзыв",
                        url="https://t.me/art_alberto",
                    )
                ]
            ]
        )
        await message.answer(
            "Добро пожаловать в Lingvéra! Откройте приложение, чтобы продолжить обучение.",
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            f"Добро пожаловать в Lingvéra! Локальное приложение: {settings.mini_app_url}\nДля кнопки Telegram Mini App настройте публичный HTTPS MINI_APP_URL."
        )


@router.message(Command("feedback"))
async def feedback(message: Message):
    await message.answer(
        "Спасибо, что помогаете улучшать Lingvéra! Напишите отзыв или сообщите об ошибке разработчику: "
        "https://t.me/art_alberto\n\n"
        "Пожалуйста, не отправляйте пароли, токены или другие секретные данные."
    )


async def main():
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN in backend/.env before starting the bot"
        )
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
