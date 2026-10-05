import os, json, logging, asyncio
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PARTSAPI_URL = "https://api.partsapi.ru/"
KEYS = {
    "getArticleCrosses": os.getenv("PARTSAPI_GETARTICLECROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getApplicability": os.getenv("PARTSAPI_GETAPPLICABILITY_KEY", "eee587e6164982e2779548362163e81d"),
    "tecdocCrosses": os.getenv("PARTSAPI_TECDOCCROSSES_KEY", "b5d5d5ed612e14256e8be426eb4df68f"),
    "VINdecodeOE": os.getenv("PARTSAPI_VINDECODEOE_KEY", "d69755043f0039590917b73e48c03aea"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("parts-ai-bot")

async def api(method, **params):
    p = dict(params)
    p.update(method=method, key=KEYS[method])
    async with httpx.AsyncClient(timeout=35) as client:
        r = await client.get(PARTSAPI_URL, params=p)
        r.raise_for_status()
        return r.json()

def compact(x, limit=3500):
    s = json.dumps(x, ensure_ascii=False, indent=2)
    return s if len(s) <= limit else s[:limit] + "\n..."

def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔎 Поиск запчасти", callback_data="search"),
            InlineKeyboardButton("🔄 Аналоги", callback_data="cross"),
        ],
        [
            InlineKeyboardButton("🚗 Поиск по VIN", callback_data="vin"),
            InlineKeyboardButton("🧩 Применяемость", callback_data="app"),
        ],
        [
            InlineKeyboardButton("📋 TecDoc-кроссы", callback_data="tecdoc"),
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
        ],
    ])

def back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
    ])

def result_menu(article):
    article = article[:100]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Аналоги", callback_data=f"cross:{article}"),
            InlineKeyboardButton("🧩 Применяемость", callback_data=f"app:{article}"),
        ],
        [InlineKeyboardButton("📋 TecDoc-кроссы", callback_data=f"tecdoc:{article}")],
        [
            InlineKeyboardButton("🔎 Новый поиск", callback_data="search"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu"),
        ],
    ])

async def start(update, context):
    context.user_data.clear()
    await update.message.reply_text("🚗 Parts AI Bot\n\nВыберите действие:", reply_markup=menu())

async def help_cmd(update, context):
    text = (
        "❓ <b>Помощь</b>\n\n"
        "🔎 Поиск запчасти — введите номер детали.\n"
        "🔄 Аналоги — поиск кроссов детали.\n"
        "🚗 VIN — расшифровка автомобиля.\n"
        "🧩 Применяемость — автомобили для детали.\n"
        "📋 TecDoc — кроссы по TecDoc.\n\n"
        "Команды: /start /vin /part /cross /app /tecdoc"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=back())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=back())

async def ask(update, context, mode):
    context.user_data["mode"] = mode
    labels = {
        "search": "🔎 Введите номер запчасти:",
        "cross": "🔄 Введите номер детали для поиска аналогов:",
        "app": "🧩 Введите номер детали для проверки применяемости:",
        "tecdoc": "📋 Введите номер детали для TecDoc-кроссов:",
        "vin": "🚗 Введите VIN автомобиля:",
    }
    text = labels[mode] + "\n\nПример: <code>123456</code>" if mode != "vin" else labels[mode] + "\n\nПример: <code>Z8TXLCW6WCM902224</code>"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=back())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=back())

async def process(update, context):
    mode = context.user_data.get("mode")
    if not mode:
        await update.message.reply_text("Выберите действие:", reply_markup=menu())
        return
    value = update.message.text.strip()
    context.user_data["mode"] = None
    try:
        if mode == "vin":
            await update.message.reply_text("⏳ Расшифровываю VIN...")
            data = await api("VINdecodeOE", vin=value.upper())
            vehicles = ((data.get("data") or {}).get("Vehicles") or [])
            v = vehicles[0] if vehicles else {}
            a = v.get("Attributes") or {}
            def val(*names):
                for n in names:
                    if v.get(n) not in (None, ""): return v[n]
                    if a.get(n) not in (None, ""): return a[n]
                return "—"
            text = (
                "🚗 <b>Автомобиль найден</b>\n\n"
                f"VIN: <code>{value.upper()}</code>\n"
                f"Марка: {val('Brand','brand')}\n"
                f"Модель: {val('Name','model')}\n"
                f"Модификация: {val('modification')}\n"
                f"Дата: {val('date')}\n"
                f"Двигатель: {val('engine')}\n"
                f"Кузов: {val('bodystyle')}\n"
                f"Рынок: {val('market')}"
            )
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=menu())
            return

        if mode == "search":
            await update.message.reply_text("⏳ Ищу запчасть...")
            data = await api("getArticleCrosses", article=value)
            title = "🔎 <b>Результат поиска</b>"
        elif mode == "cross":
            await update.message.reply_text("⏳ Ищу аналоги...")
            data = await api("getArticleCrosses", article=value)
            title = "🔄 <b>Аналоги / кроссы</b>"
        elif mode == "app":
            await update.message.reply_text("⏳ Проверяю применяемость...")
            data = await api("getApplicability", article=value)
            title = "🧩 <b>Применяемость</b>"
        else:
            await update.message.reply_text("⏳ Ищу TecDoc-кроссы...")
            data = await api("tecdocCrosses", article=value)
            title = "📋 <b>TecDoc-кроссы</b>"

        await update.message.reply_text(
            title + "\n\n" + compact(data),
            parse_mode="HTML",
            reply_markup=result_menu(value)
        )
    except Exception as e:
        log.exception("PartsAPI error")
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=menu())

async def callback(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "menu":
        context.user_data.clear()
        await q.edit_message_text("🚗 Parts AI Bot\n\nВыберите действие:", reply_markup=menu())
        return
    if data == "help":
        await help_cmd(update, context)
        return
    if data in ("search", "cross", "app", "tecdoc", "vin"):
        await ask(update, context, data)
        return

    if ":" in data:
        mode, article = data.split(":", 1)
        try:
            await q.edit_message_text("⏳ Выполняю запрос...")
            if mode == "cross":
                result = await api("getArticleCrosses", article=article)
                title = "🔄 <b>Аналоги / кроссы</b>"
            elif mode == "app":
                result = await api("getApplicability", article=article)
                title = "🧩 <b>Применяемость</b>"
            elif mode == "tecdoc":
                result = await api("tecdocCrosses", article=article)
                title = "📋 <b>TecDoc-кроссы</b>"
            else:
                return
            await q.message.reply_text(
                title + "\n\n" + compact(result),
                parse_mode="HTML",
                reply_markup=result_menu(article)
            )
        except Exception as e:
            log.exception("Callback API error")
            await q.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=menu())

async def vin_cmd(update, context):
    if context.args:
        context.user_data["mode"] = "vin"
        # Process-like inline call
        try:
            value = context.args[0].strip().upper()
            data = await api("VINdecodeOE", vin=value)
            vehicles = ((data.get("data") or {}).get("Vehicles") or [])
            v = vehicles[0] if vehicles else {}
            a = v.get("Attributes") or {}
            def val(*names):
                for n in names:
                    if v.get(n) not in (None, ""): return v[n]
                    if a.get(n) not in (None, ""): return a[n]
                return "—"
            await update.message.reply_text(
                f"🚗 <b>VIN</b>\n\nVIN: <code>{value}</code>\nМарка: {val('Brand','brand')}\nМодель: {val('Name','model')}\nМодификация: {val('modification')}\nДата: {val('date')}",
                parse_mode="HTML", reply_markup=menu()
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=menu())
    else:
        await ask(update, context, "vin")

async def part_cmd(update, context):
    if context.args:
        context.user_data["mode"] = "search"
        await process_text_value(update, context, context.args[0], "search")
    else:
        await ask(update, context, "search")

async def cross_cmd(update, context):
    if context.args:
        await process_text_value(update, context, context.args[0], "cross")
    else:
        await ask(update, context, "cross")

async def app_cmd(update, context):
    if context.args:
        await process_text_value(update, context, context.args[0], "app")
    else:
        await ask(update, context, "app")

async def tecdoc_cmd(update, context):
    if context.args:
        await process_text_value(update, context, context.args[0], "tecdoc")
    else:
        await ask(update, context, "tecdoc")

async def process_text_value(update, context, value, mode):
    try:
        if mode in ("search", "cross"):
            data = await api("getArticleCrosses", article=value)
            title = "🔎 <b>Результат</b>" if mode == "search" else "🔄 <b>Аналоги</b>"
        elif mode == "app":
            data = await api("getApplicability", article=value)
            title = "🧩 <b>Применяемость</b>"
        else:
            data = await api("tecdocCrosses", article=value)
            title = "📋 <b>TecDoc-кроссы</b>"
        await update.message.reply_text(title + "\n\n" + compact(data), parse_mode="HTML", reply_markup=result_menu(value))
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=menu())

def validate_environment():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в Environment Variables")
    log.info("TELEGRAM_BOT_TOKEN найден (значение скрыто)")
    log.info("PartsAPI keys: %s", {k: bool(v) for k, v in KEYS.items()})

async def main():
    validate_environment()
    log.info("Подключение к Telegram...")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("vin", vin_cmd))
    application.add_handler(CommandHandler("part", part_cmd))
    application.add_handler(CommandHandler("cross", cross_cmd))
    application.add_handler(CommandHandler("app", app_cmd))
    application.add_handler(CommandHandler("tecdoc", tecdoc_cmd))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process))
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram-бот успешно запущен и ожидает сообщения.")
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log.exception("КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА TELEGRAM-БОТА")
        raise
