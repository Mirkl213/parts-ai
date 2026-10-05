import os
import sqlite3
import json
import subprocess
import sys
import threading
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

DB = os.getenv("DB_PATH", "/tmp/parts_ai.db")
PARTSAPI_URL = "https://api.partsapi.ru/"

PARTSAPI_KEYS = {
    "getArticleCrosses": os.getenv(
        "PARTSAPI_GETARTICLECROSSES_KEY",
        "897a08a70828ff3a21f5e437663014d1",
    ),
    "getApplicability": os.getenv(
        "PARTSAPI_GETAPPLICABILITY_KEY",
        "eee587e6164982e2779548362163e81d",
    ),
    "tecdocCrosses": os.getenv(
        "PARTSAPI_TECDOCCROSSES_KEY",
        "b5d5d5ed612e14256e8be426eb4df68f",
    ),
    "VINdecodeOE": os.getenv(
        "PARTSAPI_VINDECODEOE_KEY",
        "d69755043f0039590917b73e48c03aea",
    ),
}

app = FastAPI(title="Parts AI Bot")

_bot_process = None


def _start_telegram_bot():
    """Start bot.py as a child process inside the same free Web Service."""
    global _bot_process
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан — Telegram-бот не запущен.")
        return

    try:
        _bot_process = subprocess.Popen(
            [sys.executable, "bot.py"],
            env=os.environ.copy(),
        )
        print(f"Telegram-бот запущен в дочернем процессе PID={_bot_process.pid}")
    except Exception:
        print("Не удалось запустить bot.py:")
        import traceback
        traceback.print_exc()


@app.on_event("startup")
async def startup_event():
    _start_telegram_bot()


@app.on_event("shutdown")
async def shutdown_event():
    global _bot_process
    if _bot_process is not None and _bot_process.poll() is None:
        _bot_process.terminate()
        try:
            _bot_process.wait(timeout=10)
        except Exception:
            _bot_process.kill()


async def partsapi_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    key = PARTSAPI_KEYS.get(method)
    if not key:
        raise HTTPException(status_code=500, detail=f"Нет API-ключа для {method}")

    payload = dict(params)
    payload["key"] = key

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(PARTSAPI_URL, data=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PartsAPI error: {e}")


class VINRequest(BaseModel):
    vin: str


class PartRequest(BaseModel):
    article: str
    brand: str = ""


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Parts AI Bot",
        "partsapi": True,
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "service": "Parts AI Bot", "partsapi": True}


@app.get("/api/vin")
async def decode_vin(vin: str = Query(..., min_length=5)):
    return await partsapi_request("VINdecodeOE", {"vin": vin})


@app.post("/api/vin")
async def decode_vin_post(body: VINRequest):
    return await partsapi_request("VINdecodeOE", {"vin": body.vin})


@app.get("/api/crosses")
async def crosses(article: str, brand: str = ""):
    return await partsapi_request(
        "getArticleCrosses",
        {"article": article, "brand": brand},
    )


@app.post("/api/crosses")
async def crosses_post(body: PartRequest):
    return await partsapi_request(
        "getArticleCrosses",
        {"article": body.article, "brand": body.brand},
    )


@app.get("/api/applicability")
async def applicability(article: str, brand: str = ""):
    return await partsapi_request(
        "getApplicability",
        {"article": article, "brand": brand},
    )


@app.get("/api/tecdoc-crosses")
async def tecdoc(article: str, brand: str = ""):
    return await partsapi_request(
        "tecdocCrosses",
        {"article": article, "brand": brand},
    )
