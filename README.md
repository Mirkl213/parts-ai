# Parts AI Bot — лучший бесплатный вариант

Эта версия НЕ использует PartsAPI, FAPI или какие-либо ранее переданные пользователем ключи.

## Источники

### 1. NHTSA vPIC
Бесплатный государственный API для VIN. Регистрация и API-ключ не нужны.
Он возвращает данные автомобиля по VIN. NHTSA также публикует локальные базы VIN-decoding.
https://vpic.nhtsa.dot.gov/api/

### 2. Open Car Parts SQLite
В проекте предусмотрена загрузка/использование открытой SQLite-базы:
https://github.com/Sepehrmasihpour/car-parts

Её модель данных: car_models, car_parts, car_part_models.
Это НЕ TecDoc и не мировая база аналогов. Поэтому бот честно сообщает,
когда кросс отсутствует.

## Архитектура

Telegram -> Render Web Service -> bot.py
                         |
                         +-> NHTSA vPIC (VIN)
                         |
                         +-> SQLite (кроссы/детали)

## Environment Variables

Только:
TELEGRAM_BOT_TOKEN

Никаких PartsAPI/FAPI ключей не требуется.

## Render

Build Command:
pip install -r requirements.txt

Start Command:
uvicorn app:app --host 0.0.0.0 --port $PORT

## Важное ограничение

Открытой бесплатной базы уровня TecDoc на 2026 год я не нашёл.
Большие cross-reference базы существуют, но это не означает, что их можно
свободно использовать/встраивать без ограничений. Поэтому эта версия не
притворяется TecDoc и использует только открытые источники.
