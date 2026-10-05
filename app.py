import os, sqlite3, json
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

DB = os.getenv("DB_PATH", "/tmp/parts_ai.db")
PARTSAPI_URL = "https://api.partsapi.ru/"

PARTSAPI_KEYS = {
    "getArticleCrosses": os.getenv("PARTSAPI_GETARTICLECROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getApplicability": os.getenv("PARTSAPI_GETAPPLICABILITY_KEY", "eee587e6164982e2779548362163e81d"),
    "tecdocCrosses": os.getenv("PARTSAPI_TECDOCCROSSES_KEY", "b5d5d5ed612e14256e8be426eb4df68f"),
    "VINdecodeOE": os.getenv("PARTSAPI_VINDECODEOE_KEY", "d69755043f0039590917b73e48c03aea"),
}

app = FastAPI(title="Parts AI Bot")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS vehicles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vin TEXT UNIQUE,
        brand TEXT,
        model TEXT,
        modification TEXT,
        date TEXT,
        raw TEXT
    )""")
    c.commit()
    c.close()

init_db()

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
    c.execute("""INSERT INTO vehicles(vin,brand,model,modification,date,raw)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
        brand=excluded.brand, model=excluded.model,
        modification=excluded.modification, date=excluded.date, raw=excluded.raw""",
        (vin, result["brand"], result["model"], result["modification"],
         result["date"], json.dumps(data, ensure_ascii=False)))
    c.commit()
    c.close()
    return result

async def crosses(article, brand=""):
    p = {"article": article}
    if brand: p["brand"] = brand
    return await partsapi_request("getArticleCrosses", **p)

async def applicability(article, car_id="", brand=""):
    p = {"article": article}
    if car_id: p["carId"] = car_id
    if brand: p["brand"] = brand
    return await partsapi_request("getApplicability", **p)

async def tecdoc(article, brand=""):
    p = {"article": article}
    if brand: p["brand"] = brand
    return await partsapi_request("tecdocCrosses", **p)

class VINRequest(BaseModel):
    vin: str

@app.get("/")
async def root():
    return {"ok": True, "service": "Parts AI Bot", "partsapi": True}

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "partsapi_keys": {k: bool(v) for k, v in PARTSAPI_KEYS.items()},
        "telegram": "running in separate Render Worker"
    }

@app.get("/api/vin")
async def api_vin(vin: str = Query(..., min_length=5, max_length=30)):
    try: return await decode_vin(vin.strip().upper())
    except Exception as e: raise HTTPException(502, str(e))

@app.post("/api/vin")
async def api_vin_post(body: VINRequest):
    try: return await decode_vin(body.vin.strip().upper())
    except Exception as e: raise HTTPException(502, str(e))

@app.get("/api/crosses")
async def api_crosses(article: str = Query(...), brand: str = ""):
    try: return await crosses(article.strip(), brand.strip())
    except Exception as e: raise HTTPException(502, str(e))

@app.get("/api/applicability")
async def api_app(article: str = Query(...), car_id: str = "", brand: str = ""):
    try: return await applicability(article.strip(), car_id.strip(), brand.strip())
    except Exception as e: raise HTTPException(502, str(e))

@app.get("/api/tecdoc-crosses")
async def api_tecdoc(article: str = Query(...), brand: str = ""):
    try: return await tecdoc(article.strip(), brand.strip())
    except Exception as e: raise HTTPException(502, str(e))
