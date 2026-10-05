import os
import subprocess
import sys
from typing import Any, Dict
import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

PARTSAPI_URL = "https://api.partsapi.ru/"

PARTSAPI_KEYS = {
    "getCrosses": os.getenv("PARTSAPI_GETCROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getArticleCrosses": os.getenv("PARTSAPI_GETARTICLECROSSES_KEY", "897a08a70828ff3a21f5e437663014d1"),
    "getApplicability": os.getenv("PARTSAPI_GETAPPLICABILITY_KEY", "eee587e6164982e2779548362163e81d"),
    "tecdocCrosses": os.getenv("PARTSAPI_TECDOCCROSSES_KEY", "b5d5d5ed612e14256e8be426eb4df68f"),
    "VINdecodeOE": os.getenv("PARTSAPI_VINDECODEOE_KEY", "d69755043f0039590917b73e48c03aea"),
}

app = FastAPI(title="Parts AI Bot")
_bot_process = None

def start_bot():
    global _bot_process
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("TELEGRAM_BOT_TOKEN не задан — Telegram-бот не запущен.")
        return
    _bot_process = subprocess.Popen([sys.executable, "bot.py"], env=os.environ.copy())
    print(f"Telegram-бот запущен в дочернем процессе PID={_bot_process.pid}")

@app.on_event("startup")
async def startup():
    start_bot()

@app.on_event("shutdown")
async def shutdown():
    global _bot_process
    if _bot_process and _bot_process.poll() is None:
        _bot_process.terminate()

async def partsapi_request(method: str, params: Dict[str, Any]):
    key = PARTSAPI_KEYS[method]
    query = {"method": method, "key": key}
    query.update({k: v for k, v in params.items() if v is not None and v != ""})
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(PARTSAPI_URL, params=query)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"PartsAPI HTTP {e.response.status_code}: {e.response.text[:700]}",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PartsAPI error: {e}")

class VINRequest(BaseModel):
    vin: str

class PartRequest(BaseModel):
    article: str
    brand: str = ""

@app.get("/")
def root():
    return {"ok": True, "service": "Parts AI Bot", "partsapi": True, "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN"))}

@app.get("/api/health")
def health():
    return {"ok": True, "service": "Parts AI Bot", "partsapi": True}

@app.get("/api/vin")
async def vin(vin: str = Query(..., min_length=5)):
    return await partsapi_request("VINdecodeOE", {"vin": vin})

@app.post("/api/vin")
async def vin_post(body: VINRequest):
    return await partsapi_request("VINdecodeOE", {"vin": body.vin})

@app.get("/api/crosses")
async def crosses(article: str):
    return await partsapi_request("getCrosses", {"number": article})

@app.post("/api/crosses")
async def crosses_post(body: PartRequest):
    return await partsapi_request("getCrosses", {"number": body.article})

@app.get("/api/applicability")
async def applicability(article: str, brand: str):
    return await partsapi_request("getApplicability", {"sku": article, "brand": brand})

@app.get("/api/tecdoc-crosses")
async def tecdoc(article: str):
    return await partsapi_request("tecdocCrosses", {"number": article})
