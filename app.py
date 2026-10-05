import os, sqlite3, json, asyncio, threading
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

DB = os.getenv("DB_PATH", "/tmp/parts_ai.db")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PARTSAPI_URL = "https://api.partsapi.ru/"

# ВНИМАНИЕ: это тестовые ключи, ранее переданные в чат.
# Для продакшена рекомендуется перевыпустить их после публикации.
PARTSAPI_KEYS = {
    "getArticleCrosses": "897a08a70828ff3a21f5e437663014d1",
    "getApplicability": "eee587e6164982e2779548362163e81d",
    "tecdocCrosses": "b5d5d5ed612e14256e8be426eb4df68f",
    "VINdecodeOE": "d69755043f0039590917b73e48c03aea",
}

app = FastAPI(title="Parts AI Bot")

# ---------------- DB ----------------

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS vehicles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin TEXT UNIQUE,
            brand TEXT,
            model TEXT,
            modification TEXT,
            date TEXT,
            raw TEXT
        )
    """)
    c.commit()
    c.close()

init_db()

# ---------------- PartsAPI ----------------

async def partsapi_request(method: str, **params) -> Dict[str, Any]:
    key = PARTSAPI_KEYS[method]
    p = dict(params)
    p.update(method=method, key=key)

    async with httpx.AsyncClient(timeout=35) as client:
        r = await client.get(PARTSAPI_URL, params=p)
        r.raise_for_status()
        return r.json()

def val(o, *names):
    for n in names:
        if o.get(n) not in (None, ""):
            return o[n]
    return ""

async def decode_vin(vin):
    data = await partsapi_request("VINdecodeOE", vin=vin)
    vehicles = ((data.get("data") or {}).get("Vehicles") or [])
    vehicle = vehicles[0] if vehicles else {}
    attrs = vehicle.get("Attributes") or {}

    result = {
        "vin": vin,
        "brand": val(vehicle, "Brand") or val(attrs, "brand"),
        "model": val(vehicle, "Name") or val(attrs, "model"),
        "modification": val(attrs, "modification") or val(vehicle, "Name"),
        "date": val(attrs, "date"),
        "engine": val(attrs, "engine"),
        "body": val(attrs, "bodystyle"),
        "market": val(attrs, "market"),
        "catalog": val(vehicle, "Catalog") or val(attrs, "catalog"),
        "vehicle_id": val(vehicle, "VehicleId"),
        "raw": data,
    }

    if not result["brand"] and not result["model"]:
        raise RuntimeError("PartsAPI не вернул автомобиль для этого VIN")

    c = db()
    c.execute("""
        INSERT INTO vehicles(vin,brand,model,modification,date,raw)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
            brand=excluded.brand,
            model=excluded.model,
            modification=excluded.modification,
            date=excluded.date,
            raw=excluded.raw
    """, (
        vin, result["brand"], result["model"],
        result["modification"], result["date"],
        json.dumps(data, ensure_ascii=False)
    ))
    c.commit()
    c.close()

    return result

async def crosses(article, brand=""):
    p = {"article": article}
    if brand:
        p["brand"] = brand
    return await partsapi_request("getArticleCrosses", **p)

async def applicability(article, car_id="", brand=""):
    p = {"article": article}
    if car_id:
        p["carId"] = car_id
    if brand:
        p["brand"] = brand
    return await partsapi_request("getApplicability", **p)

async def tecdoc(article, brand=""):
    p = {"article": article}
    if brand:
        p["brand"] = brand
    return await partsapi_request("tecdocCrosses", **p)

def compact(x, limit=3500):
    s = json.dumps(x, ensure_ascii=False, indent=2)
    return s if len(s) <= limit else s[:limit] + "\n..."

# ---------------- FastAPI ----------------

class VINRequest(BaseModel):
    vin: str

@app.get("/")
async def root():
    return {"ok": True, "service": "Parts AI Bot", "partsapi": True}

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "telegram_token": bool(TOKEN),
        "partsapi_keys": {k: bool(v) for k, v in PARTSAPI_KEYS.items()}
    }

@app.get("/api/vin")
async def api_vin(vin: str = Query(..., min_length=5, max_length=30)):
    try:
        return await decode_vin(vin.strip().upper())
    except Exception as e:
        raise HTTPException(502, str(e))

@app.post("/api/vin")
async def api_vin_post(body: VINRequest):
    try:
        return await decode_vin(body.vin.strip().upper())
    except Exception as e:
        raise HTTPException(502, str(e))

@app.get("/api/crosses")
async def api_crosses(article: str = Query(...), brand: str = ""):
    try:
        return await crosses(article.strip(), brand.strip())
    except Exception as e:
        raise HTTPException(502, str(e))

@app.get("/api/applicability")
async def api_app(article: str = Query(...), car_id: str = "", brand: str = ""):
    try:
        return await applicability(article.strip(), car_id.strip(), brand.strip())
    except Exception as e:
        raise HTTPException(502, str(e))

@app.get("/api/tecdoc-crosses")
async def api_tecdoc(article: str = Query(...), brand: str = ""):
    try:
        return await tecdoc(article.strip(), brand.strip())
    except Exception as e:
        raise HTTPException(502, str(e))

# ---------------- Telegram UI ----------------

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔎 Поиск запчасти", callback_data="search_part"),
            InlineKeyboardButton("🔄 Найти аналоги", callback_data="cross_part"),
        ],
        [
            InlineKeyboardButton("🚗 Поиск по VIN", callback_data="vin_search"),
            InlineKeyboardButton("🧩 Применяемость", callback_data="applicability"),
        ],
        [
            InlineKeyboardButton("📋 TecDoc-кроссы", callback_data="tecdoc"),
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
        ],
    ])

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
    ])

def result_menu(article: str):
    # article хранится только в callback_data, поэтому ограничиваем длину
    safe = article[:120]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔄 Найти аналоги",
                callback_data=f"res_cross:{safe}"
            ),
            InlineKeyboardButton(
                "🧩 Применяемость",
                callback_data=f"res_app:{safe}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 TecDoc-кроссы",
                callback_data=f"res_tecdoc:{safe}"
            )
        ],
        [
            InlineKeyboardButton("🔎 Новый поиск", callback_data="search_part"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu"),
        ]
    ])

def vin_result_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔎 Искать запчасть", callback_data="search_part"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu"),
        ]
    ])

async def show_menu(update: Update, text="🚗 Parts AI Bot\n\nВыберите действие:"):
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            text=text,
            reply_markup=main_menu()
        )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_menu(update)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ Как пользоваться ботом\n\n"
        "🔎 Поиск запчасти — введите оригинальный номер детали.\n"
        "🔄 Найти аналоги — найдёт кроссы детали.\n"
        "🚗 Поиск по VIN — расшифрует VIN через PartsAPI.\n"
        "🧩 Применяемость — покажет автомобили, для которых подходит деталь.\n"
        "📋 TecDoc-кроссы — поиск кроссов по TecDoc.\n\n"
        "Можно также использовать команды:\n"
        "/vin VIN\n"
        "/part НОМЕР\n"
        "/cross НОМЕР\n"
        "/app НОМЕР\n"
        "/tecdoc НОМЕР"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=back_menu())
    else:
        await update.message.reply_text(text, reply_markup=back_menu())

async def ask_part(update, context, mode):
    context.user_data["mode"] = mode
    labels = {
        "search": "🔎 Введите номер запчасти для поиска:",
        "cross": "🔄 Введите номер запчасти для поиска аналогов:",
        "app": "🧩 Введите номер запчасти для проверки применяемости:",
        "tecdoc": "📋 Введите номер запчасти для поиска TecDoc-кроссов:",
    }
    text = labels[mode] + "\n\nНапример: <code>123456</code>"
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=back_menu()
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=back_menu()
        )

async def vin_ask(update, context):
    context.user_data["mode"] = "vin"
    text = (
        "🚗 <b>Поиск по VIN</b>\n\n"
        "Введите VIN автомобиля.\n"
        "Например:\n<code>Z8TXLCW6WCM902224</code>"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, parse_mode="HTML", reply_markup=back_menu()
        )
    else:
        await update.message.reply_text(
            text=text, parse_mode="HTML", reply_markup=back_menu()
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        await update.message.reply_text(
            "Выберите действие в меню 👇",
            reply_markup=main_menu()
        )
        return

    value = update.message.text.strip()
    if not value:
        return

    # После получения запроса возвращаем пользователя в нейтральное состояние.
    context.user_data["last_article"] = value
    context.user_data["mode"] = None

    try:
        if mode == "vin":
            await update.message.reply_text("⏳ Расшифровываю VIN...")
            v = await decode_vin(value.upper())
            text = (
                "🚗 <b>Автомобиль найден</b>\n\n"
                f"VIN: <code>{v['vin']}</code>\n"
                f"Марка: {v['brand'] or '—'}\n"
                f"Модель: {v['model'] or '—'}\n"
                f"Модификация: {v['modification'] or '—'}\n"
                f"Дата: {v['date'] or '—'}\n"
                f"Двигатель: {v['engine'] or '—'}\n"
                f"Кузов: {v['body'] or '—'}\n"
                f"Рынок: {v['market'] or '—'}"
            )
            await update.message.reply_text(
                text=text, parse_mode="HTML", reply_markup=vin_result_menu()
            )
            return

        if mode == "search":
            await update.message.reply_text("⏳ Ищу информацию по запчасти...")
            data = await crosses(value)
            text = "🔎 <b>Результат поиска</b>\n\n" + compact(data)
            await update.message.reply_text(
                text=text, parse_mode="HTML",
                reply_markup=result_menu(value)
            )
            return

        if mode == "cross":
            await update.message.reply_text("⏳ Ищу аналоги...")
            data = await crosses(value)
            text = "🔄 <b>Аналоги / кроссы</b>\n\n" + compact(data)
            await update.message.reply_text(
                text=text, parse_mode="HTML",
                reply_markup=result_menu(value)
            )
            return

        if mode == "app":
            await update.message.reply_text("⏳ Проверяю применяемость...")
            data = await applicability(value)
            text = "🧩 <b>Применяемость</b>\n\n" + compact(data)
            await update.message.reply_text(
                text=text, parse_mode="HTML",
                reply_markup=result_menu(value)
            )
            return

        if mode == "tecdoc":
            await update.message.reply_text("⏳ Ищу TecDoc-кроссы...")
            data = await tecdoc(value)
            text = "📋 <b>TecDoc-кроссы</b>\n\n" + compact(data)
            await update.message.reply_text(
                text=text, parse_mode="HTML",
                reply_markup=result_menu(value)
            )
            return

    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при обращении к PartsAPI:\n\n{e}",
            reply_markup=main_menu()
        )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "menu":
        context.user_data.clear()
        await show_menu(update)
        return

    if data == "help":
        await help_cmd(update, context)
        return

    if data == "search_part":
        await ask_part(update, context, "search")
        return

    if data == "cross_part":
        await ask_part(update, context, "cross")
        return

    if data == "applicability":
        await ask_part(update, context, "app")
        return

    if data == "tecdoc":
        await ask_part(update, context, "tecdoc")
        return

    if data == "vin_search":
        await vin_ask(update, context)
        return

    if data.startswith("res_cross:"):
        article = data.split(":", 1)[1]
        try:
            await q.edit_message_text("⏳ Ищу аналоги...")
            result = await crosses(article)
            await q.message.reply_text(
                "🔄 <b>Аналоги / кроссы</b>\n\n" + compact(result),
                parse_mode="HTML",
                reply_markup=result_menu(article)
            )
        except Exception as e:
            await q.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())
        return

    if data.startswith("res_app:"):
        article = data.split(":", 1)[1]
        try:
            await q.edit_message_text("⏳ Проверяю применяемость...")
            result = await applicability(article)
            await q.message.reply_text(
                "🧩 <b>Применяемость</b>\n\n" + compact(result),
                parse_mode="HTML",
                reply_markup=result_menu(article)
            )
        except Exception as e:
            await q.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())
        return

    if data.startswith("res_tecdoc:"):
        article = data.split(":", 1)[1]
        try:
            await q.edit_message_text("⏳ Ищу TecDoc-кроссы...")
            result = await tecdoc(article)
            await q.message.reply_text(
                "📋 <b>TecDoc-кроссы</b>\n\n" + compact(result),
                parse_mode="HTML",
                reply_markup=result_menu(article)
            )
        except Exception as e:
            await q.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())
        return

# ---------------- Compatibility commands ----------------

async def vin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await vin_ask(update, context)
        return
    context.user_data["mode"] = None
    try:
        v = await decode_vin(context.args[0].strip().upper())
        await update.message.reply_text(
            f"VIN: {v['vin']}\n"
            f"Марка: {v['brand'] or '—'}\n"
            f"Модель: {v['model'] or '—'}\n"
            f"Модификация: {v['modification'] or '—'}\n"
            f"Дата: {v['date'] or '—'}\n"
            f"Двигатель: {v['engine'] or '—'}\n"
            f"Кузов: {v['body'] or '—'}\n"
            f"Рынок: {v['market'] or '—'}",
            reply_markup=vin_result_menu()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка VINdecodeOE:\n{e}", reply_markup=main_menu())

async def part_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await ask_part(update, context, "search")
        return
    article = context.args[0]
    try:
        data = await crosses(article, context.args[1] if len(context.args) > 1 else "")
        await update.message.reply_text(
            "🔎 <b>Результат поиска</b>\n\n" + compact(data),
            parse_mode="HTML",
            reply_markup=result_menu(article)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())

async def cross_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await ask_part(update, context, "cross")
        return
    try:
        data = await crosses(context.args[0])
        await update.message.reply_text(
            "🔄 <b>Аналоги / кроссы</b>\n\n" + compact(data),
            parse_mode="HTML",
            reply_markup=result_menu(context.args[0])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())

async def app_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await ask_part(update, context, "app")
        return
    try:
        data = await applicability(context.args[0])
        await update.message.reply_text(
            "🧩 <b>Применяемость</b>\n\n" + compact(data),
            parse_mode="HTML",
            reply_markup=result_menu(context.args[0])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())

async def tecdoc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await ask_part(update, context, "tecdoc")
        return
    try:
        data = await tecdoc(context.args[0])
        await update.message.reply_text(
            "📋 <b>TecDoc-кроссы</b>\n\n" + compact(data),
            parse_mode="HTML",
            reply_markup=result_menu(context.args[0])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{e}", reply_markup=main_menu())

# ---------------- Bot runner ----------------

async def run_bot():
    if not TOKEN:
        return

    b = Application.builder().token(TOKEN).build()

    b.add_handler(CommandHandler("start", start_cmd))
    b.add_handler(CommandHandler("help", help_cmd))
    b.add_handler(CommandHandler("vin", vin_cmd))
    b.add_handler(CommandHandler("part", part_cmd))
    b.add_handler(CommandHandler("cross", cross_cmd))
    b.add_handler(CommandHandler("app", app_cmd))
    b.add_handler(CommandHandler("tecdoc", tecdoc_cmd))

    b.add_handler(CallbackQueryHandler(callback_handler))
    b.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await b.initialize()
    await b.start()
    await b.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await b.updater.stop()
        await b.stop()
        await b.shutdown()

if __name__ == "__main__":
    if TOKEN:
        threading.Thread(
            target=lambda: asyncio.run(run_bot()),
            daemon=True
        ).start()

    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000"))
    )
