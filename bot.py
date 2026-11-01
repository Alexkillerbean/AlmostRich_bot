"""
Бот «Почти Богат» — выдача доступа к калькулятору стоимости жизни.

Порядок запуска:
1. Скопируйте .env.example в .env и заполните значения.
2. pip install -r requirements.txt
3. python bot.py

.env в репозиторий НЕ коммитить — там живёт токен.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

import db

# --- Конфигурация (из .env, файл не хранится в git) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")            # токен от @BotFather
CHANNEL_ID = os.getenv("CHANNEL_ID")          # @username канала или -100xxxxxxxxxx
WEB_APP_URL = os.getenv("WEB_APP_URL")          # https://... (адрес мини-аппа)

if not BOT_TOKEN or not CHANNEL_ID or not WEB_APP_URL:
    raise RuntimeError(
        "Переменные BOT_TOKEN, CHANNEL_ID, WEB_APP_URL должны быть заданы "
        "в .env (см. .env.example)."
    )

CHANNEL_URL = f"https://t.me/{CHANNEL_ID.lstrip('@')}"

# --- Тексты ---
SUBSCRIBE_CAPTION = (
    "Сначала — подписка на канал. Это несложно, обещаем."
)
WELCOME_CAPTION = (
    "Доступ открыт. Калькулятор уже ждёт — кнопка ниже 👇"
)
HELP_TEXT = (
    "Что умею:\n"
    "• Проверяю подписку на канал и открываю доступ к калькулятору стоимости жизни.\n"
    "• Команда /start — заново проверить доступ.\n\n"
    "Вопросы и идеи — в канал, там всё читают."
)
ERROR_TEXT = "Что-то пошло не так. Попробуйте позже или напишите в канал."

BANNERS_DIR = Path(__file__).parent / "banners"
BANNER_SUBSCRIBE = BANNERS_DIR / "subscribe.png"
BANNER_WELCOME = BANNERS_DIR / "welcome.png"

# Кэш file_id отправленных баннеров, чтобы не грузить файл повторно.
_banner_file_ids: dict[str, str] = {}


def _kb_subscribe() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="Я подписался — проверить", callback_data="check_sub")],
    ])


def _kb_open_app() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Открыть калькулятор",
            web_app=WebAppInfo(url=WEB_APP_URL),
        )],
    ])


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """True, если пользователь подписан на канал. При любой ошибке API — False."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest:
        return False


async def _send_banner(message: Message, path: Path, caption: str,
                       reply_markup: InlineKeyboardMarkup) -> None:
    """Отправить баннер с кэшированием file_id; при ошибке редактирования — новым сообщением."""
    key = path.name
    file_id = _banner_file_ids.get(key)
    try:
        if file_id:
            await message.answer_photo(photo=file_id, caption=caption,
                                       reply_markup=reply_markup)
        else:
            sent = await message.answer_photo(photo=FSInputFile(path),
                                              caption=caption,
                                              reply_markup=reply_markup)
            _banner_file_ids[key] = sent.photo[-1].file_id
    except TelegramBadRequest:
        # Сообщение слишком старое для редактирования или file_id протух — отправляем заново.
        sent = await message.answer_photo(photo=FSInputFile(path),
                                          caption=caption,
                                          reply_markup=reply_markup)
        _banner_file_ids[key] = sent.photo[-1].file_id


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    await db.touch_user(message.from_user.id, message.from_user.username)
    await db.update_last_seen(message.from_user.id)
    if await is_subscribed(bot, message.from_user.id):
        await db.mark_subscribed(message.from_user.id)
        await _send_banner(message, BANNER_WELCOME, WELCOME_CAPTION, _kb_open_app())
    else:
        await _send_banner(message, BANNER_SUBSCRIBE, SUBSCRIBE_CAPTION, _kb_subscribe())


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, bot: Bot) -> None:
    await db.update_last_seen(callback.from_user.id)
    if await is_subscribed(bot, callback.from_user.id):
        await db.mark_subscribed(callback.from_user.id)
        await _send_banner(callback.message, BANNER_WELCOME, WELCOME_CAPTION, _kb_open_app())
    else:
        await callback.answer("Подписки пока не видно. Подпишитесь и нажмите снова.",
                              show_alert=True)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await db.update_last_seen(message.from_user.id)
    await message.answer(HELP_TEXT)


@router.error()
async def error_handler(event, exception) -> None:
    logging.exception("Ошибка обработчика: %s", exception)
    if isinstance(event, Message):
        await event.answer(ERROR_TEXT)
    elif isinstance(event, CallbackQuery) and event.message:
        await event.message.answer(ERROR_TEXT)


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await db.init()

    bot = Bot(token=BOT_TOKEN)
    await bot.set_my_commands([
        # ("/start", "Проверить доступ к калькулятору"),
        # ("/help", "Помощь"),
    ])

    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
