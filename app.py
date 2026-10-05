import os,sqlite3,asyncio,logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from telegram import Update,ReplyKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,ContextTypes,filters

DB=os.getenv("DB_PATH","/tmp/parts_ai.db"); TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
VEH=[(1,"BMW","3 Series F30",2015,"320d","Sedan","Automatic"),(2,"Volkswagen","Golf VII",2016,"1.6 TDI","Hatchback","Manual"),(3,"Toyota","Camry XV70",2018,"2.5","Sedan","Automatic")]
PART=[("Передние тормозные колодки BMW 3 F30","Brembo","P06049","от 85 €"),("Ступичный подшипник BMW 3 F30","FAG","713 6674 10","от 110 €"),("Масляный фильтр BMW 320d","MANN","HU 816 X","от 18 €"),("Передние тормозные колодки Golf VII","TRW","GDB1957","от 55 €"),("Масляный фильтр Toyota Camry 2.5","Toyota","90915-YZZD2","от 12 €")]

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,make,model,year,engine,body,transmission)")
        c.execute("CREATE TABLE IF NOT EXISTS parts(id INTEGER PRIMARY KEY AUTOINCREMENT,name,brand,oem,price)")
        if not c.execute("SELECT count(*) FROM vehicles").fetchone()[0]: c.executemany("INSERT INTO vehicles VALUES(?,?,?,?,?,?,?)",VEH)
        if not c.execute("SELECT count(*) FROM parts").fetchone()[0]: c.executemany("INSERT INTO parts(name,brand,oem,price) VALUES(?,?,?,?)",PART)
def search(table,q):
    with db() as c:
        if table=="vehicles":
            s=f"%{q}%"; return [dict(x) for x in c.execute("SELECT * FROM vehicles WHERE make LIKE ? OR model LIKE ? OR engine LIKE ? OR body LIKE ? OR CAST(year AS TEXT) LIKE ? LIMIT 10",(s,)*5)]
        s=f"%{q}%"; return [dict(x) for x in c.execute("SELECT * FROM parts WHERE name LIKE ? OR brand LIKE ? OR oem LIKE ? LIMIT 10",(s,)*3)]
def vin(v):
    v=v.replace(" ","").upper()
    if len(v)!=17:return None
    for p,x in zip(("WBA","WVW","JT"),VEH):
        if v.startswith(p): return dict(zip(("id","make","model","year","engine","body","transmission"),x))
app=FastAPI(title="PARTS AI")
class VIN(BaseModel): vin:str
@app.on_event("startup")
async def start():
    init()
    if TOKEN: asyncio.create_task(bot())

@app.get("/",response_class=HTMLResponse)
async def home(): return HTML
@app.get("/api/health")
async def health(): return {"ok":True,"telegram":bool(TOKEN)}
@app.get("/api/vehicles")
async def vehicles(q:str=""): return search("vehicles",q)
@app.get("/api/parts")
async def parts(q:str=""): return search("parts",q)
@app.post("/api/vin")
async def api_vin(x:VIN): return vin(x.vin) or {"error":"VIN не найден в демо-базе"}

def kb(): return ReplyKeyboardMarkup([["🚗 Автомобиль","🔎 VIN"],["🔧 Запчасть","❓ Помощь"]],resize_keyboard=True)
async def start(u:Update,c:ContextTypes.DEFAULT_TYPE):
    c.user_data["mode"]=None
    await u.message.reply_text("👋 PARTS AI\n\nВыберите действие или отправьте VIN.",reply_markup=kb())
async def help_(u,c): await u.message.reply_text("Команды: /start /vin /car /part\n\nМожно написать название детали, например «колодки».",reply_markup=kb())
async def do_vin(u,t):
    x=vin(t)
    if not x:return await u.message.reply_text("❌ VIN не найден. В демо доступны WBA, WVW и JT.")
    await u.message.reply_text(f"✅ {x['make']} {x['model']}\n📅 {x['year']} · ⚙️ {x['engine']} · 🚗 {x['body']} · 🔄 {x['transmission']}",reply_markup=kb())
async def vin_cmd(u,c):
    if c.args:return await do_vin(u," ".join(c.args))
    c.user_data["mode"]="vin"; await u.message.reply_text("🔎 Отправьте 17-значный VIN.")
async def car_cmd(u,c): c.user_data["mode"]="car"; await u.message.reply_text("🚗 Например: BMW 3 Series 2015 320d")
async def part_cmd(u,c): c.user_data["mode"]="part"; await u.message.reply_text("🔧 Напишите название детали или OEM-номер.")
async def text(u,c):
    t=u.message.text.strip()
    if t=="❓ Помощь": return await help_(u,c)
    if t=="🔎 VIN": c.user_data["mode"]="vin"; return await u.message.reply_text("🔎 Отправьте VIN.")
    if t=="🚗 Автомобиль": return await car_cmd(u,c)
    if t=="🔧 Запчасть": return await part_cmd(u,c)
    m=c.user_data.get("mode")
    if m=="vin": c.user_data["mode"]=None; return await do_vin(u,t)
    if m=="car":
        c.user_data["mode"]=None; xs=search("vehicles",t)
        msg="🚗 Автомобили:\n\n"+"\n".join(f"• {x['make']} {x['model']} {x['year']} — {x['engine']}" for x in xs[:5]) if xs else "❌ Не найдено"
        return await u.message.reply_text(msg,reply_markup=kb())
    xs=search("parts",t)
    msg="🔧 Запчасти:\n\n"+"\n".join(f"• {x['name']}\n  {x['brand']} | OEM {x['oem']} | {x['price']}" for x in xs[:8]) if xs else "❌ Ничего не найдено"
    await u.message.reply_text(msg,reply_markup=kb())
async def bot():
    try:
        a=Application.builder().token(TOKEN).build()
        for h in [CommandHandler("start",start),CommandHandler("help",help_),CommandHandler("vin",vin_cmd),CommandHandler("car",car_cmd),CommandHandler("part",part_cmd)]: a.add_handler(h)
        a.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,text))
        await a.initialize(); await a.start(); await a.updater.start_polling()
        while True: await asyncio.sleep(3600)
    except Exception: logging.exception("Telegram error")

HTML="""<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>PARTS AI</title><style>body{font-family:Arial;max-width:760px;margin:auto;padding:20px;background:#f4f6f8}section{background:white;padding:18px;margin:12px 0;border-radius:16px}input,button{padding:13px;font-size:16px;border-radius:10px}input{width:95%}button{margin-top:7px;background:#17202a;color:white}li{margin:12px 0}</style><h1>🚗 PARTS AI</h1><section><h2>🔎 VIN</h2><input id=v placeholder='17 символов'><button onclick=v()>Определить</button><p id=vo></p></section><section><h2>🚘 Автомобиль</h2><input id=c placeholder='BMW 3 Series 2015 320d'><button onclick=c()>Найти</button><div id=co></div></section><section><h2>🔧 Запчасть</h2><input id=p placeholder='Колодки, фильтр, OEM...'><button onclick=p()>Найти</button><div id=po></div></section><p>Демо-каталог. Реальный TecDoc/поставщики подключаются через API.</p><script>const e=s=>String(s??'').replace(/[&<>]/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[x]));async function v(){let x=await(await fetch('/api/vin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vin:document.querySelector('#v').value})})).json();vo.innerHTML=x.error?'❌ '+e(x.error):`✅ ${e(x.make)} ${e(x.model)} · ${x.year} · ${e(x.engine)}`}async function c(){let x=await(await fetch('/api/vehicles?q='+encodeURIComponent(document.querySelector('#c').value))).json();co.innerHTML=x.map(a=>`<p>🚘 <b>${e(a.make)} ${e(a.model)}</b> — ${a.year}, ${e(a.engine)}</p>`).join('')||'❌ Не найдено'}async function p(){let x=await(await fetch('/api/parts?q='+encodeURIComponent(document.querySelector('#p').value))).json();po.innerHTML=x.map(a=>`<p>🔧 <b>${e(a.name)}</b><br>${e(a.brand)} · OEM ${e(a.oem)} · ${e(a.price)}</p>`).join('')||'❌ Не найдено'}</script>"""
init()
