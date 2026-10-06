import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB = DATA / "carparts.db"


def norm(x):
    return re.sub(r"[^A-Z0-9А-ЯЁ]+", "", (x or "").upper())


def _tables(con):
    return {
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]


def _model_candidates(con, manufacturer, model):
    """Find likely model rows using only the local open DB."""
    if "car_models" not in _tables(con):
        return []

    cols = _columns(con, "car_models")
    if "id" not in cols or "name" not in cols:
        return []

    wanted = (model or "").upper()
    # VIN decoder returns forms such as "Golf V/VI / Jetta".
    # Search the individual model families, not the whole formatted string.
    tokens = re.findall(r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9-]{2,}", wanted)
    tokens = [t for t in tokens if t not in {"VOLKSWAGEN", "AUDI", "SEAT", "SKODA"}]
    if not tokens and wanted:
        tokens = [wanted]

    rows = []
    for token in tokens[:5]:
        like = f"%{token}%"
        rows.extend(
            con.execute(
                "SELECT id, name FROM car_models WHERE UPPER(name) LIKE ? LIMIT 100",
                (like,),
            ).fetchall()
        )

    # Manufacturer-aware filtering when the model table contains a brand/make column.
    brand_cols = [c for c in cols if c.lower() in {"make", "brand", "manufacturer", "maker"}]
    if brand_cols and manufacturer:
        bc = brand_cols[0]
        filtered = []
        for rid, name in rows:
            try:
                r = con.execute(
                    f"SELECT {bc} FROM car_models WHERE id=?", (rid,)
                ).fetchone()
                if r and r[0] and manufacturer.upper() in str(r[0]).upper():
                    filtered.append((rid, name))
            except Exception:
                pass
        if filtered:
            rows = filtered

    seen = set()
    out = []
    for rid, name in rows:
        if rid in seen:
            continue
        seen.add(rid)
        out.append({"id": rid, "name": name})
    return out


def check_applicability(article, manufacturer, model, year=None):
    """
    Conservative local fitment check.

    confirmed:
      the local open DB links the requested part to a vehicle model matching
      the VIN-decoded model family.

    not_confirmed:
      the part is absent from the local vehicle-part relations, or the
      vehicle model cannot be matched.

    This never treats a cross-reference as proof of fitment.
    """
    result = {
        "article": article,
        "manufacturer": manufacturer,
        "model": model,
        "year": year,
        "status": "not_confirmed",
        "matched_vehicles": [],
        "reason": "",
        "source": "local_open_carparts_db",
    }

    if not DB.exists():
        result["reason"] = "Локальная открытая БД запчастей ещё не загружена."
        return result

    with sqlite3.connect(DB) as con:
        tables = _tables(con)
        required = {"car_parts", "car_part_models", "car_models"}
        if not required.issubset(tables):
            result["reason"] = "В локальной БД нет таблиц связи деталь → автомобиль."
            return result

        pcols = _columns(con, "car_parts")
        if "id" not in pcols or "part_number" not in pcols:
            result["reason"] = "Структура таблицы деталей не поддерживается."
            return result

        a = norm(article)
        part_rows = con.execute(
            """
            SELECT id, part_number, name
            FROM car_parts
            WHERE REPLACE(REPLACE(REPLACE(UPPER(part_number),' ',''),'-',''),'.','') = ?
            LIMIT 50
            """,
            (a,),
        ).fetchall()

        if not part_rows:
            result["reason"] = "Номер детали не найден в локальной открытой БД."
            return result

        model_rows = _model_candidates(con, manufacturer, model)
        if not model_rows:
            result["reason"] = "VIN-модель не найдена среди моделей локальной БД."
            return result

        model_ids = {r["id"] for r in model_rows}
        placeholders = ",".join("?" for _ in model_ids)

        matches = con.execute(
            f"""
            SELECT DISTINCT p.part_number, p.name, c.name
            FROM car_parts p
            JOIN car_part_models x ON x.part_id=p.id
            JOIN car_models c ON c.id=x.car_id
            WHERE x.part_id IN ({",".join("?" for _ in part_rows)})
              AND c.id IN ({placeholders})
            LIMIT 100
            """,
            [r[0] for r in part_rows] + list(model_ids),
        ).fetchall()

        if matches:
            result["status"] = "confirmed_by_local_db"
            result["matched_vehicles"] = [
                {"article": r[0], "name": r[1], "vehicle": r[2]}
                for r in matches
            ]
            result["reason"] = (
                "Номер детали связан с совпадающей моделью в локальной "
                "открытой БД. Это подтверждение по локальному набору данных, "
                "а не гарантия полной OEM/TecDoc применяемости."
            )
        else:
            result["reason"] = (
                "Деталь найдена, но связь с данной VIN-моделью в локальной "
                "открытой БД не найдена."
            )

    return result
