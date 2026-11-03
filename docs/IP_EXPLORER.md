# IP Explorer

GET `/api/v1/ips/{IPv4-or-IPv6}?from=...&to=...` возвращает статистику выбранного
периода: events, types/categories, target hosts/ports, paths, HTTP status и SSH
outcomes, hourly chronology, findings. Поддерживает те же dimension filters,
что events. IPv4-mapped IPv6 канонизируется. Невалидный IP — 422, отсутствующая
история — пустой ответ, expired detail — 410.

Распределения ограничены top 100, поля truncated явные; null port/path/status
не выдумываются и не попадают в списки известных значений. Общий count точный.
retained_first_seen/retained_last_seen берутся из сохранённых hourly rollups
по IP без фильтра периода; first_seen/last_seen — внутри выбранного периода.
Хронология IP Explorer строится по detail (по умолчанию 30d). Для более старых
периодов используйте History и сохранённые агрегаты: [RETENTION.md](RETENTION.md).

Переход из Timeline сохраняет time range в hash URL. Доступны ручной IP,
1h/24h/7d/30d и произвольный UTC диапазон. Срабатывания открываются с evidence.
GeoIP/ASN provider Protocol готов, default provider возвращает unavailable/null;
внешних lookup и фиктивных геоданных нет. Геолокация характеризует сеть IP.

Проверены API IPv6, distributions, counts, empty, invalid IP и отсутствующий GeoIP;
Ruff/mypy; frontend lint/types/tests/build. Browser smoke включён в release checks.
