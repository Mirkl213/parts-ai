# Parts AI Bot — multi-brand / free local data

Этот вариант не использует PartsAPI или FAPI.

## Что добавлено
- офлайн VIN-декодер WMI для разных марок;
- локальный движок кроссреференсов `data/crosses.sqlite`;
- seed-набор подтверждённых связей для Toyota 90915-YZZD1 и его замен;
- отдельная кнопка `🔁 Кроссы / аналоги`;
- API `GET /api/crosses?article=...`;
- нормализация номеров: пробелы, дефисы, точки и регистр не мешают поиску.

## Важно про бесплатные данные
Полной открытой TecDoc-аналогичной базы с десятками миллионов кроссов, которую можно законно положить в бесплатный Render-сервис, найти не удалось. Большой публичный cross-reference проект, найденный при проверке, содержит около 80 млн строк, но распространяет полный дамп как платный продукт. Поэтому мы не притворяемся, что используем его бесплатно.

Вместо этого бот построен так, чтобы локальная база кроссов расширялась CSV-файлами без изменения кода. Текущий seed — только подтверждённые связи для тестового номера `90915-YZZD1`.

## Render
Build Command:
`pip install -r requirements.txt`

Start Command:
`uvicorn app:app --host 0.0.0.0 --port $PORT`

Environment:
`TELEGRAM_BOT_TOKEN`

## Sources / attribution
- NHTSA vPIC: https://vpic.nhtsa.dot.gov/api/
- Open vehicle dataset: https://github.com/vehiclesdb/vehiclesdb
- Cross-reference seed was assembled from public cross-reference pages used only as verification references; it is not presented as a complete catalog.

## v6
- Исправлен модельный год для современных Volkswagen: `WV...` + код `C` → 2012.
- В VIN-ответ добавлены поля двигателя, коробки и привода.
- Если открытые данные не позволяют определить силовую часть надёжно, бот показывает «Не определён по VIN», а не угадывает.


## v7
Telegram polling теперь запускается внутри FastAPI-процесса через async lifecycle. Отдельный subprocess для bot.py удалён, чтобы Render не оставлял второй getUpdates-процесс и Telegram Conflict.
