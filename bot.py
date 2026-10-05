import os
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("parts-ai-bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

PARTSAPI_URL = "https://api.partsapi.ru/"
KEYS = {
    "getArticleCrosses": os.getenv("PARTSAPI_GETARTICLECROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getApplicability": os.getenv("PARTSAPI_GETAPPLICABILITY_KEY", "eee587e6164982e2779548362163e81d"),
    "tecdocCrosses": os.getenv("PARTSAPI_TECDOCCROSSES_KEY", "b5d5d5ed612e14256e8be426eb4df68f"),
    "VINdecodeOE": os.getenv("PARTSAPI_VINDECODEOE_KEY", "d69755043f0039590917b73e48c03aea"),
}

MODES = {}


async def api_call(method: str, params: dict):
    data = dict(params)
    data["key"] = KEYS[method]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(PARTSAPI_URL, data=data)
        r.raise_for_status()
        return r.json()


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Поиск запчасти", callback_data="part")],
        [InlineKeyboardButton("🔄 Аналоги", callback_data="cross")],
        [InlineKeyboardButton("🚗 Поиск по VIN", callback_data="vin")],
        [InlineKeyboardButton("🧩 Применяемость", callback_data="app")],
        [InlineKeyboardButton("📋 TecDoc-кроссы", callback_data="tecdoc")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для поиска автозапчастей.\nВыбери действие:",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери нужное действие в меню. Можно искать по артикулу, "
        "получать аналоги, применяемость, TecDoc-кроссы или расшифровывать VIN.",
        reply_markup=main_menu(),
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data

    if action == "help":
        await q.message.reply_text(
            "Примеры:\n"
            "• Аналоги: Bosch 0986479...\n"
            "• VIN: введи 17 символов\n"
            "• Применяемость: артикул\n"
            "• TecDoc-кроссы: артикул",
            reply_markup=main_menu(),
        )
        return

    MODES[q.from_user.id] = action
    prompts = {
        "part": "Введи артикул запчасти.",
        "cross": "Введи артикул для поиска аналогов.",
        "vin": "Введи VIN-код (обычно 17 символов).",
        "app": "Введи артикул для проверки применяемости.",
        "tecdoc": "Введи артикул для TecDoc-кроссов.",
    }
    await q.message.reply_text(prompts[action])


async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mode = MODES.get(user_id)

    if not mode:
        await update.message.reply_text("Выбери действие:", reply_markup=main_menu())
        return

    value = update.message.text.strip()
    try:
        if mode == "vin":
            result = await api_call("VINdecodeOE", {"vin": value})
        elif mode == "cross":
            result = await api_call("getArticleCrosses", {"article": value})
        elif mode == "app":
            result = await api_call("getApplicability", {"article": value})
        elif mode == "tecdoc":
            result = await api_call("tecdocCrosses", {"article": value})
        else:
            result = await api_call("getArticleCrosses", {"article": value})

        text = str(result)
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        await update.message.reply_text(text, reply_markup=main_menu())

    except Exception as e:
        log.exception("Ошибка запроса")
        await update.message.reply_text(
            f"Не удалось получить ответ от PartsAPI.\nОшибка: {e}",
            reply_markup=main_menu(),
        )


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в Environment Variables")

    log.info("TELEGRAM_BOT_TOKEN найден (значение скрыто)")
    log.info("Подключение к Telegram...")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CallbackQueryHandler(menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_text))

    log.info("Telegram-бот успешно запущен и ожидает сообщения.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
