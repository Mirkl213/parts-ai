import os
import sqlite3
import logging
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles"
DB = os.path.join(os.path.dirname(__file__), "data", "parts.db")
MODES = {}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("parts-bot")


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 VIN", callback_data="vin")],
        [InlineKeyboardButton("🔄 Аналоги", callback_data="cross")],
        [InlineKeyboardButton("🔎 Деталь по автомобилю", callback_data="vehicle_parts")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])


async def decode_vin(vin):
    url = f"{VPIC}/DecodeVinValuesExtended/{vin}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params={"format": "json"})
        r.raise_for_status()
        return r.json()


def find_crosses(article):
    a = article.strip().upper().replace(" ", "").replace("-", "")
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT brand, cross_article, cross_brand, source
            FROM cross_refs
            WHERE REPLACE(REPLACE(UPPER(article),' ',''),'-','')=?
               OR REPLACE(REPLACE(UPPER(cross_article),' ',''),'-','')=?
            LIMIT 50
        """, (a, a)).fetchall()
    return rows


def find_vehicle_parts(vehicle):
    with sqlite3.connect(DB) as con:
        return con.execute("""
            SELECT article, name, brand, source
            FROM vehicle_parts
            WHERE UPPER(vehicle) LIKE ?
            ORDER BY article
            LIMIT 50
        """, (f"%{vehicle.upper()}%",)).fetchall()


def fmt_vin(data):
    rows = data.get("Results") or []
    if not rows:
        return "VIN не найден."
    r = rows[0]
    pairs = [
        ("Марка", r.get("Make")),
        ("Модель", r.get("Model")),
        ("Год", r.get("ModelYear")),
        ("Кузов", r.get("BodyClass")),
        ("Двигатель", r.get("EngineModel")),
        ("Объём", r.get("DisplacementL")),
        ("Топливо", r.get("FuelTypePrimary")),
        ("Привод", r.get("DriveType")),
        ("КПП", r.get("TransmissionStyle")),
    ]
    out = ["🚗 Автомобиль"]
    for k, v in pairs:
        if v:
            out.append(f"• {k}: {v}")
    return "\n".join(out)


async def start(update, context):
    await update.message.reply_text(
        "Привет! Это бесплатная версия на открытых данных.\nВыбери действие:",
        reply_markup=menu(),
    )


async def callback(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "help":
        await q.message.reply_text(
            "🚗 VIN — NHTSA vPIC.\n"
            "🔄 Аналоги — локальная SQLite-база.\n"
            "🔎 Детали — локальная база совместимости.\n"
            "База может пополняться без платного API.",
            reply_markup=menu(),
        )
        return

    MODES[q.from_user.id] = q.data
    prompts = {
        "vin": "Введи VIN (17 символов).",
        "cross": "Введи номер детали.",
        "vehicle_parts": "Введи марку/модель для поиска деталей в локальной базе.",
    }
    await q.message.reply_text(prompts[q.data])


async def process(update, context):
    uid = update.effective_user.id
    mode = MODES.get(uid)
    value = update.message.text.strip()

    if not mode:
        await update.message.reply_text("Выбери действие:", reply_markup=menu())
        return

    try:
        if mode == "vin":
            if len(value) != 17:
                await update.message.reply_text("VIN должен содержать 17 символов.")
                return
            text = fmt_vin(await decode_vin(value.upper()))

        elif mode == "cross":
            rows = find_crosses(value)
            if not rows:
                text = (
                    "🔄 В локальной базе кроссы не найдены.\n\n"
                    "Это не означает, что аналогов нет — просто номер пока отсутствует "
                    "в открытой базе."
                )
            else:
                lines = ["🔄 Найденные кроссы:"]
                for brand, article, cross_brand, source in rows:
                    lines.append(f"• {brand or '—'} → {article} ({cross_brand or '—'})")
                text = "\n".join(lines)

        else:
            rows = find_vehicle_parts(value)
            if not rows:
                text = "В локальной базе детали для этого автомобиля не найдены."
            else:
                lines = ["🔎 Детали:"]
                for article, name, brand, source in rows:
                    title = f"{name} — " if name else ""
                    lines.append(f"• {title}{article} [{brand or '—'}]")
                text = "\n".join(lines)

        if len(text) > 3900:
            text = text[:3900] + "\n…"
        await update.message.reply_text(text, reply_markup=menu())

    except Exception as e:
        log.exception("Ошибка")
        await update.message.reply_text(f"Ошибка: {e}", reply_markup=menu())


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process))
    log.info("Бот на открытых данных запущен.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
