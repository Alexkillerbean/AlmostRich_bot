"""
Бот «Почти Богат» — выдача доступа к калькулятору стоимости жизни.

Запуск:
1. Скопируйте .env.example в .env и заполните значения (локально).
   На хостинге значения задаются в панели (переменные окружения).
2. pip install -r requirements.txt
3. python bot.py
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ErrorEvent,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from dotenv import load_dotenv

load_dotenv()  # локально читаем .env; на хостинге переменные уже в окружении

import db

# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")      # @username канала или -100xxxxxxxxxx
WEB_APP_URL = os.getenv("WEB_APP_URL")    # https://... (мини-апп)

if not BOT_TOKEN or not CHANNEL_ID or not WEB_APP_URL:
    raise RuntimeError(
        "Переменные BOT_TOKEN, CHANNEL_ID, WEB_APP_URL должны быть заданы "
        "в окружении (см. .env.example)."
    )

if CHANNEL_ID.startswith("@"):
    CHANNEL_URL = f"https://t.me/{CHANNEL_ID.lstrip('@')}"
elif CHANNEL_ID.startswith("http"):
    CHANNEL_URL = CHANNEL_ID  # ссылка-приглашение для приватного канала
else:
    raise RuntimeError(
        "CHANNEL_ID должен быть @username канала или ссылкой-приглашением "
        "(https://t.me/+...). Числовой ID в кнопку подписки не подставить."
    )

# --- Тексты ---
SUBSCRIBE_CAPTION = "Сначала — подписка на канал. Это несложно, обещаем."
WELCOME_CAPTION = "Доступ открыт. Калькулятор уже ждёт — кнопка ниже 👇"
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
    """True, если пользователь состоит в канале. Любая ошибка API -> False."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
        # «Заглушённые» участники: status='restricted', но is_member=True
        return member.status == "restricted" and bool(getattr(member, "is_member", False))
    except TelegramAPIError:
        return False


async def _send_banner(message: Message | None, path: Path, caption: str,
                       reply_markup: InlineKeyboardMarkup) -> None:
    """Баннер с кэшированием file_id. message=None (старое сообщение) — молча выходим."""
    if message is None:
        return
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
    except TelegramAPIError:
        sent = await message.answer_photo(photo=FSInputFile(path),
                                          caption=caption,
                                          reply_markup=reply_markup)
        _banner_file_ids[key] = sent.photo[-1].file_id


router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


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
        await callback.answer()  # снимаем «часики» на кнопке
        await _send_banner(callback.message, BANNER_WELCOME, WELCOME_CAPTION, _kb_open_app())
    else:
        await callback.answer("Подписки пока не видно. Подпишитесь и нажмите снова.",
                              show_alert=True)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await db.update_last_seen(message.from_user.id)
    await message.answer(HELP_TEXT)


@router.error()
async def error_handler(event: ErrorEvent) -> None:
    logging.exception("Ошибка обработчика: %s", event.exception)
    msg = event.update.message
    if msg is None and event.update.callback_query is not None:
        msg = event.update.callback_query.message
    if msg is not None:
        try:
            await msg.answer(ERROR_TEXT)
        except TelegramAPIError:
            pass


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await db.init()

    bot = Bot(token=BOT_TOKEN)
    await bot.set_my_commands([
        BotCommand(command="start", description="Проверить доступ к калькулятору"),
        BotCommand(command="help", description="Помощь"),
    ])

    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
