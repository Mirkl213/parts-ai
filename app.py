import os, subprocess, sys, sqlite3, re
from pathlib import Path
import httpx
from fastapi import FastAPI, Query
from pydantic import BaseModel
from eu_vin import decode

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB = DATA / "carparts.db"
OLD_DB = DATA / "parts.db"
OPEN_DB_URL = "https://github.com/Sepehrmasihpour/car-parts/raw/refs/heads/master/car-pwa/public/carparts.db"

app = FastAPI(title="Parts AI Bot — EU Free Data")
_bot_process = None

def db_ready():
    return DB.exists() and DB.stat().st_size > 10000

async def ensure_open_db():
    DATA.mkdir(parents=True, exist_ok=True)
    if db_ready():
        return
    tmp = DATA / "carparts.db.tmp"
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            r = await client.get(OPEN_DB_URL)
            r.raise_for_status()
            tmp.write_bytes(r.content)
        tmp.replace(DB)
        print(f"Open car-parts DB downloaded: {DB.stat().st_size/1024/1024:.1f} MB")
    except Exception as e:
        print("Не удалось загрузить открытую БД:", e)
        if tmp.exists(): tmp.unlink(missing_ok=True)

def start_bot():
    global _bot_process
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        return
    _bot_process = subprocess.Popen([sys.executable, "bot.py"], env=os.environ.copy())

@app.on_event("startup")
async def startup():
    await ensure_open_db()
    start_bot()

@app.on_event("shutdown")
async def shutdown():
    if _bot_process and _bot_process.poll() is None:
        _bot_process.terminate()

@app.get("/")
def root():
    return {"ok": True, "service": "Parts AI Bot — EU Free Data", "open_db": db_ready()}

@app.get("/api/health")
def health():
    return {"ok": True, "open_db": db_ready(), "db_mb": round(DB.stat().st_size/1024/1024,1) if DB.exists() else 0}

@app.get("/api/vin")
def vin(vin: str = Query(..., min_length=17, max_length=17)):
    return decode(vin)

class VINRequest(BaseModel):
    vin: str

@app.post("/api/vin")
def vin_post(body: VINRequest):
    return decode(body.vin)

def norm(x):
    return re.sub(r"[\s\-_./]", "", (x or "").upper())

def tables():
    if not DB.exists(): return set()
    with sqlite3.connect(DB) as con:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def find_part(article):
    a = norm(article)
    if not DB.exists(): return []
    ts = tables()
    if not {"car_parts","car_part_models","car_models"} <= ts: return []
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT p.part_number, p.name, c.name, c.id
            FROM car_parts p
            LEFT JOIN car_part_models x ON x.part_id=p.id
            LEFT JOIN car_models c ON c.id=x.car_id
            WHERE REPLACE(REPLACE(REPLACE(UPPER(p.part_number),' ',''),'-',''),'.','') LIKE ?
            ORDER BY p.part_number, c.name LIMIT 100
        """, (f"%{a}%",)).fetchall()
    return [{"article":r[0],"name":r[1],"vehicle":r[2]} for r in rows]

def vehicle_parts(vehicle):
    if not DB.exists(): return []
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT DISTINCT p.part_number, p.name, c.name
            FROM car_models c
            JOIN car_part_models x ON x.car_id=c.id
            JOIN car_parts p ON p.id=x.part_id
            WHERE UPPER(c.name) LIKE ?
            ORDER BY p.part_number LIMIT 200
        """, (f"%{vehicle.upper()}%",)).fetchall()
    return [{"article":r[0],"name":r[1],"vehicle":r[2]} for r in rows]
