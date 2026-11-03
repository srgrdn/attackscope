# Реализованный API v0.1

JSON, RFC3339 UTC (выход Z), ranges [from,to). API base /api/v1.
Default UI proxy публикует только read endpoints; ingestion физически отдельный
ASGI listener8001. OpenAPI read app доступен внутри Docker на8000/openapi.json.
UI не требует отдельного token только при localhost single-operator запуске.

## Входы

| Method/path | Назначение | Границы |
|---|---|---|
| GET /health/live | ASGI liveness | оба listeners |
| GET /health/ready | DB/schema/WAL/FK ready | UI proxy /api/v1/health/ready |
| POST /api/v1/ingest/events | authenticated atomic batch |1MiB,1..500,source token |
| GET /api/v1/hosts | hosts |limit1..500,UUID cursor |
| GET /api/v1/events | filtered events |limit1..500,keyset cursor15m |
| GET /api/v1/events/{UUID} | sanitized detail |404 after detail TTL |
| GET /api/v1/timeline | events or exact buckets |target_buckets20..500,default60 |
| GET /api/v1/findings | explainable detections |500 max,truncated flag |
| GET /api/v1/ips/{IP} | IP detail analytics |IPv4/IPv6,top100 distributions |
| GET /api/v1/overview | totals/distributions/activity |10s/32-query internal cache |
| GET /api/v1/history | hourly/daily aggregates |full UTC hours,top100 dimensions |
| GET /api/v1/events/export.csv | full filtered CSV |10000 events/8MiB,atomic |
| GET /api/v1/events/export.json | full filtered JSON |same bounds,atomic |

## Общие фильтры read API

`from` и `to` обязательны (hosts/detail UUID исключение). Default detail retention30d.
AND filters: `host_id` UUID, `ip` canonical source IP, `source` ssh/http/firewall,
`category` ssh_authentication/ssh_connection/http_request/firewall_packet,
`port` destination0..65535, `severity` info/low/medium/high.
Unknown query keys запрещены. `sort=timestamp`, `order=asc|desc`; иные SQL sort
не принимаются. Cursor/limit действуют только на events, export cursor отвергает.
IP path — authority над query ip. Historical severity не поддерживается (422).

Events response: items, next_cursor, coverage.detail_available_from.
Cursor фиксирует received_at watermark, timestamp/id position, filter fingerprint,
expiry; не является auth credential. При expired курсоре перезапустить pagination.
В public event нет source_id/token_digest; attributes и safe_original очищены.

Timeline: mode=events|buckets,total,items,buckets,bucket_seconds.
Detail threshold min(1500,target_buckets*3); иначе groups
{from,to,source,category,count}. Boundary buckets обрезаются до выбранного range,
counts берутся только из [from,to), без интерполяции. Zoom делает новый запрос.
Findings отдельным endpoint; id/rule/name/version/window/count/reason/evidenceIDs≤100.

IP: выбранный period count, first/last внутри него и retained first/last по rollups;
types/hosts/ports/paths/statuses/outcomes/activity/findings. Enrichment default
unavailable/null, не внешняя geolocation. Overview отдельно считает все HTTP и
подозрительные HTTP; worker асинхронный. Все top lists имеют truncated.

History: до aggregate retention365d, from округляется вверх до часа, to вниз;
coverage.kind=hourly_rollups, effective_from/to, partial_hours_excluded=true.
Counts точные для этого effective range, buckets hourly≤31d/daily дальше.
Path/status/outcome/severity/raw fields недоступны; см. RETENTION.md.

## Ingestion contract

Bearer sourceUUID.secret256bits, token хранится только у агента, DB содержит SHA256.
Host/kind проверяются до сохранения. JSON array envelope:

```json
[{"transport_version":1,"source":"http","source_reference":"example:1","payload":{"timestamp":"2026-11-03T00:00:00Z","remote_addr":"2001:db8::10","request_method":"GET","path":"/missing","status":404}}]
```

HTTP structured payload, SSH outcome и firewall fields описаны INGESTION.md.
SSH/firewall допускают payload {timestamp,journal_message}; bounded parser
немедленно заменяет его безопасными полями. Оригинальный MESSAGE не сохраняется.
Unknown format отклоняет batch. Source_reference stable — идемпотентно в пределах
TTL, без stable ID гарантии dedup нет. Result accepted/duplicates/schema_version.
Clock range: detail cutoff .. now+5m. Compression disabled; 2xx только после commit.

В GET /api/v1/findings у sensitive_path v2 reason дополнительно содержит
matched_paths (до 20 строк) и matched_paths_truncated. Старые findings могут
не содержать эти поля. Версия правила относится к finding, schema_version события
остаётся 1. UI-пометка возможной операторской проверки не является полем API
или основанием для исключения события из экспорта/статистики.

## Ошибки

Формат {error:{code,message,request_id}}, без payload/SQL/token.
401 credentials,403 host/kind,408 body timeout,410 expired detail/cursor/history,
413 body/export limit,415 encoding/type,422 validation/range/filters,
429 source/concurrency limits,503 busy storage/query deadline. Retry-After для
временных app limits. Proxy/Uvicorn могут вернуть собственный bounded 4xx/503.
Автоматический агент повторяет временные ошибки с паузой; permanent4xx требует
оператора. SQL errors откатывают transaction. Экспорт при ошибке не выдаёт часть файла.
