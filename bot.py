import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from eu_vin import decode
from app import find_part, vehicle_parts
from cross_db import find as find_crosses
from fitment import check_applicability

TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
MODES={}
telegram_app=None
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 VIN Европа", callback_data="vin")],
        [InlineKeyboardButton("🔎 Найти деталь", callback_data="part")],
        [InlineKeyboardButton("🔁 Кроссы / аналоги", callback_data="cross")],
        [InlineKeyboardButton("✅ Применяемость", callback_data="fitment")],
        [InlineKeyboardButton("🚘 Детали по авто", callback_data="vehicle")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ])

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Бот работает на открытой локальной БД.\n"
        "VIN: европейский офлайн-декодер.\n"
        "Запчасти: открытая SQLite-база совместимости.",
        reply_markup=menu())

async def callback(update, context):
    q=update.callback_query
    await q.answer()
    if q.data=="help":
        await q.message.reply_text(
            "🚗 VIN — страна, производитель, год, WMI и модель там, где её можно честно определить.\n"
            "🔎 Деталь — поиск номера и автомобилей, где он встречается в открытой БД.\n"
            "🚘 Детали по авто — список деталей из открытой БД.\n\n"
            "Важно: это не TecDoc и не лицензированная OEM-база.", reply_markup=menu())
        return
    MODES[q.from_user.id]=q.data
    if q.data == "fitment":
        MODES[q.from_user.id] = {"mode": "fitment", "step": "vin"}

    prompts={"vin":"Введи VIN из 17 символов.","part":"Введи номер детали.","vehicle":"Введи марку или модель, например: Golf, A4, Octavia.","cross":"Введи OEM или артикул, например: 90915-YZZD1.","fitment":"Введи VIN из 17 символов."}
    await q.message.reply_text(prompts[q.data])

async def process(update, context):
    uid=update.effective_user.id
    mode=MODES.get(uid)
    value=update.message.text.strip()
    if not mode:
        await update.message.reply_text("Выбери действие:",reply_markup=menu()); return
    try:
        # Applicability is a two-step flow: VIN, then article.
        if isinstance(mode, dict) and mode.get("mode") == "fitment":
            if mode.get("step") == "vin":
                r = decode(value)
                mode["vin"] = r
                mode["step"] = "article"
                MODES[uid] = mode
                await update.message.reply_text(
                    "🚗 Автомобиль определён:\n"
                    f"• {r['manufacturer']}\n"
                    f"• {r.get('model') or 'Модель не определена'}\n"
                    f"• Модельный год: {', '.join(map(str, r.get('year_candidates') or [])) or 'не определён'}\n\n"
                    "Теперь введи номер детали для проверки применяемости."
                )
                return
            r = mode["vin"]
            year = (r.get("year_candidates") or [None])[0]
            result = check_applicability(
                value, r.get("manufacturer"), r.get("model"), year
            )
            if result["status"] == "confirmed_by_local_db":
                lines = [
                    f"✅ Применяемость: {value}",
                    f"• Авто: {r.get('manufacturer')}",
                    f"• Модель: {r.get('model') or 'не определена'}",
                    f"• Модельный год: {year or 'не определён'}",
                    "• Статус: подтверждено локальной БД",
                ]
                for x in result["matched_vehicles"][:10]:
                    lines.append(f"• {x['vehicle']}")
                lines.append("\n⚠️ Это подтверждение только по нашей открытой локальной БД, не полная TecDoc/OEM-гарантия.")
            else:
                lines = [
                    f"⚠️ Применяемость: {value}",
                    f"• Авто: {r.get('manufacturer')}",
                    f"• Модель: {r.get('model') or 'не определена'}",
                    f"• Модельный год: {year or 'не определён'}",
                    "• Статус: НЕ ПОДТВЕРЖДЕНО",
                    f"• Причина: {result['reason']}",
                    "\nКросс детали сам по себе не считается подтверждением применяемости."
                ]
            MODES.pop(uid, None)
            text="\n".join(lines)
        elif mode=="vin":
            r=decode(value)
            lines=["🚗 VIN","• Производитель: "+r["manufacturer"]]
            if r["country"]: lines.append("• Страна: "+r["country"])
            if r["model"]: lines.append("• Модель: "+r["model"])
            lines += ["• Регион: "+str(r["region"] or "не определён"),
                      "• Модельный год: "+", ".join(map(str,r["year_candidates"])),
                      "• WMI: "+r["wmi"], "• Завод: "+r["plant_code"],
                      "• Серийный номер: "+r["serial"]]
            text="\n".join(lines)
        elif mode=="part":
            rows=find_part(value)
            if not rows:
                text="🔎 В открытой БД этот номер не найден."
            else:
                lines=["🔎 Деталь: "+value]
                seen=set()
                for x in rows:
                    key=(x["article"],x["name"],x["vehicle"])
                    if key in seen: continue
                    seen.add(key)
                    line=f"• {x['article']}"
                    if x["name"]: line+=f" — {x['name']}"
                    if x["vehicle"]: line+=f" → {x['vehicle']}"
                    lines.append(line)
                text="\n".join(lines)
        elif mode=="cross":
            rows=find_crosses(value)
            if not rows:
                text="🔁 Для этого номера пока нет записи в нашей открытой локальной базе кроссов."
            else:
                lines=[f"🔁 Кроссы для: {value}"]
                seen=set()
                for x in rows:
                    key=(x["brand"],x["article"])
                    if key in seen: continue
                    seen.add(key)
                    lines.append(f"• {x['brand']}: {x['article']}")
                lines.append("\n⚠️ Кроссреференс не заменяет проверку применяемости по авто/двигателю.")
                text="\n".join(lines)
        else:
            rows=vehicle_parts(value)
            if not rows:
                text="🚘 В открытой БД детали для этого авто не найдены."
            else:
                lines=[f"🚘 Детали для: {value}"]
                seen=set()
                for x in rows:
                    if x["article"] in seen: continue
                    seen.add(x["article"])
                    lines.append(f"• {x['article']}"+(f" — {x['name']}" if x["name"] else ""))
                text="\n".join(lines)
        await update.message.reply_text(text[:3900],reply_markup=menu())
    except Exception as e:
        logging.exception("bot error")
        await update.message.reply_text("Ошибка: "+str(e),reply_markup=menu())

async def start_telegram():
    global telegram_app
    if not TOKEN:
        logging.warning("TELEGRAM_BOT_TOKEN не задан — Telegram polling отключён")
        return
    telegram_app=Application.builder().token(TOKEN).build()
    telegram_app.add_handler(CommandHandler("start",start))
    telegram_app.add_handler(CommandHandler("help",start))
    telegram_app.add_handler(CallbackQueryHandler(callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,process))
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    logging.info("Telegram polling started inside FastAPI process")

async def stop_telegram():
    global telegram_app
    if telegram_app is None:
        return
    try:
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    finally:
        telegram_app=None
        logging.info("Telegram polling stopped")

def main():
    if not TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,process))
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
