import os
import subprocess
import sys
import sqlite3
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "parts.db"
OPEN_DB_URL = "https://github.com/Sepehrmasihpour/car-parts/raw/refs/heads/master/car-pwa/public/carparts.db"
VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles"

app = FastAPI(title="Parts AI Bot - Free Open Data")
_bot_process = None


def init_local_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS cross_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article TEXT NOT NULL,
            brand TEXT NOT NULL,
            cross_article TEXT NOT NULL,
            cross_brand TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'local'
        );
        CREATE INDEX IF NOT EXISTS idx_cross_article ON cross_refs(article);
        CREATE INDEX IF NOT EXISTS idx_cross_brand_article ON cross_refs(brand, article);
        CREATE TABLE IF NOT EXISTS vehicle_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle TEXT NOT NULL,
            article TEXT NOT NULL,
            name TEXT,
            brand TEXT,
            source TEXT NOT NULL DEFAULT 'local'
        );
        CREATE INDEX IF NOT EXISTS idx_vehicle ON vehicle_parts(vehicle);
        CREATE INDEX IF NOT EXISTS idx_vehicle_article ON vehicle_parts(vehicle, article);
        """)


def start_bot():
    global _bot_process
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("TELEGRAM_BOT_TOKEN не задан — бот не запущен.")
        return
    _bot_process = subprocess.Popen([sys.executable, "bot.py"], env=os.environ.copy())
    print(f"Telegram-бот PID={_bot_process.pid}")


@app.on_event("startup")
async def startup():
    init_local_db()
    start_bot()


@app.on_event("shutdown")
async def shutdown():
    if _bot_process and _bot_process.poll() is None:
        _bot_process.terminate()


async def vpic_decode(vin: str):
    url = f"{VPIC}/DecodeVinValuesExtended/{vin}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params={"format": "json"})
        r.raise_for_status()
        return r.json()


def local_crosses(article: str):
    a = article.strip().upper().replace(" ", "").replace("-", "")
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT brand, cross_article, cross_brand, source
            FROM cross_refs
            WHERE REPLACE(REPLACE(UPPER(article),' ',''),'-','')=?
               OR REPLACE(REPLACE(UPPER(cross_article),' ',''),'-','')=?
            LIMIT 100
        """, (a, a)).fetchall()
    return [
        {"brand": r[0], "article": r[1], "cross_brand": r[2], "source": r[3]}
        for r in rows
    ]


def vehicle_parts(vehicle: str):
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT article, name, brand, source
            FROM vehicle_parts
            WHERE UPPER(vehicle) LIKE ?
            ORDER BY article
            LIMIT 100
        """, (f"%{vehicle.upper()}%",)).fetchall()
    return [{"article": r[0], "name": r[1], "brand": r[2], "source": r[3]} for r in rows]


class VINRequest(BaseModel):
    vin: str


@app.get("/")
def root():
    return {"ok": True, "service": "Parts AI Bot - Free Open Data", "vpic": True, "local_db": DB.exists()}


@app.get("/api/health")
def health():
    return {"ok": True, "vpic": True, "local_db": DB.exists()}


@app.get("/api/vin")
async def vin(vin: str = Query(..., min_length=17, max_length=17)):
    return await vpic_decode(vin.upper())


@app.post("/api/vin")
async def vin_post(body: VINRequest):
    return await vpic_decode(body.vin.strip().upper())


@app.get("/api/crosses")
def crosses(article: str):
    return {"source": "local SQLite", "results": local_crosses(article)}


@app.get("/api/vehicle-parts")
def parts(vehicle: str):
    return {"source": "local SQLite", "results": vehicle_parts(vehicle)}
