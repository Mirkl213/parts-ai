# Parts AI Bot — EU Free Data

Версия без PartsAPI и FAPI.

## Источники

1. European/offline VIN decoder — правила на основе открытого проекта Quomation/vin-decoder (Apache-2.0).
2. Parts/vehicle compatibility — `Sepehrmasihpour/car-parts`, SQLite `carparts.db`.

База carparts.db скачивается при старте, если её ещё нет.

## Render

Build:
`pip install -r requirements.txt`

Start:
`uvicorn app:app --host 0.0.0.0 --port $PORT`

Environment:
`TELEGRAM_BOT_TOKEN`

## Что умеет

- VIN европейского формата: WMI, страна, производитель, год-кандидаты, завод, серийный номер.
- Для VW/Audi/SEAT/Škoda с европейским `ZZZ` — дополнительные модели по открытым правилам.
- Поиск номера детали в открытой SQLite-БД.
- Поиск деталей по марке/модели.

## Ограничение

Это не TecDoc и не полноценная лицензированная OEM-база. Открытая carparts.db содержит связи автомобиль ↔ деталь, но не является полноценной базой aftermarket-кроссов. Поэтому бот не будет выдумывать аналоги.

## Следующий этап

Можно отдельно добавить второй легальный открытый источник именно для OEM/aftermarket cross-reference, если найдём датасет с разрешённым распространением.

## Важное исправление v2

- Подключена открытая WMI-база `Wal33D/nhtsa-vin-decoder` (MIT).
- Исправлена логика года по позиции 7/10 VIN.
- Добавлен `Z8T = Mitsubishi` для европейского производства.
- Для VIN `Z8TXLCW6WCM902224` код года `C` с буквенной позицией 7 трактуется как 2012, а не как 1982.


## v3
Исправлена ошибка `string index out of range`: функция определения года теперь получает полный VIN и дополнительно проверяет длину входных данных.
