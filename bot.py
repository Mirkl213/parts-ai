
import os
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger("parts-ai-bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = "https://api.partsapi.ru/"
KEYS = {
    "getCrosses": os.getenv("PARTSAPI_GETCROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getApplicability": os.getenv("PARTSAPI_GETAPPLICABILITY_KEY", "eee587e6164982e2779548362163e81d"),
    "tecdocCrosses": os.getenv("PARTSAPI_TECDOCCROSSES_KEY", "b5d5d5ed612e14256e8be426eb4df68f"),
    "VINdecodeOE": os.getenv("PARTSAPI_VINDECODEOE_KEY", "d69755043f0039590917b73e48c03aea"),
}
MODES = {}

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Аналоги", callback_data="cross")],
        [InlineKeyboardButton("🚗 Поиск по VIN", callback_data="vin")],
        [InlineKeyboardButton("🧩 Применяемость", callback_data="app")],
        [InlineKeyboardButton("📋 TecDoc-кроссы", callback_data="tecdoc")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])

async def api_call(method, params):
    data = dict(params)
    data["key"] = KEYS[method]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(URL, data=data)
        r.raise_for_status()
        return r.json()

async def start(update, context):
    await update.message.reply_text("Привет! Выбери действие:", reply_markup=menu())

async def callback(update, context):
    q = update.callback_query
    await q.answer()
    action = q.data
    if action == "help":
        await q.message.reply_text(
            "Аналоги — введи номер детали.\n"
            "VIN — введи VIN/номер рамы.\n"
            "Применяемость — введи артикул и бренд через |, например: 12345|BOSCH.\n"
            "TecDoc-кроссы — введи номер детали.",
            reply_markup=menu(),
        )
        return
    MODES[q.from_user.id] = action
    prompts = {
        "cross": "Введи артикул детали.",
        "vin": "Введи VIN или номер рамы.",
        "app": "Введи артикул и бренд через |. Например: 12345|BOSCH",
        "tecdoc": "Введи артикул детали.",
    }
    await q.message.reply_text(prompts[action])

async def process(update, context):
    uid = update.effective_user.id
    mode = MODES.get(uid)
    if not mode:
        await update.message.reply_text("Выбери действие:", reply_markup=menu())
        return
    value = update.message.text.strip()
    try:
        if mode == "cross":
            result = await api_call("getCrosses", {"number": value})
        elif mode == "vin":
            result = await api_call("VINdecodeOE", {"vin": value})
        elif mode == "app":
            parts = [x.strip() for x in value.split("|", 1)]
            if len(parts) != 2 or not parts[1]:
                await update.message.reply_text("Нужно: артикул|бренд\nНапример: 12345|BOSCH")
                return
            result = await api_call("getApplicability", {"sku": parts[0], "brand": parts[1]})
        else:
            result = await api_call("tecdocCrosses", {"number": value})
        text = str(result)
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        await update.message.reply_text(text, reply_markup=menu())
    except Exception as e:
        log.exception("Ошибка запроса")
        await update.message.reply_text(f"Не удалось получить ответ от PartsAPI.\nОшибка: {e}", reply_markup=menu())

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в Environment Variables")
    log.info("TELEGRAM_BOT_TOKEN найден (значение скрыто)")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", lambda u, c: start(u, c)))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process))
    log.info("Telegram-бот успешно запущен и ожидает сообщения.")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
