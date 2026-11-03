# Этап 2 — Event Storage & API

Статус: реализован; перед Этапом 3 требуется согласование следующего плана.

## Реализовано

- Alembic `0002_event_storage`: hosts, sources, events, delivery_keys, event_rollups,
  pending_events и индексы для времени, host/IP/category/source/port, received_at.
- Единый публичный Pydantic EventOut: UUID, UTC, IPv4/IPv6, nullable fields,
  versioned schema, безопасная проекция исходных структурированных данных.
- Structured JSON payloads SSH/HTTP/Firewall с allowlist и удалением query/fragment,
  Authorization/Cookie/неизвестных полей, ограничением display fields.
- Индивидуальные source secrets, constant-time digest comparison, привязка kind/host,
  проверка отзыва credentials и в write transaction.
- POST ingestion: atomic batch, body/batch/source/global/queue limits, deadlines,
  early validation, safe errors, request IDs и безопасные server logs.
- Пакетные executemany INSERT, BEGIN IMMEDIATE, атомарные dedup/pending records и
  hourly upserts. Дубликаты не увеличивают event counts или pending work.
- GET hosts/events/event detail с фильтрами, bounded reads, keyset pages и snapshot
  watermark. UI proxy пропускает read routes, ingestion не публикуется.
- Локальный CLI create-host/create-source/disable-source, private token files без
  перезаписи и symlinks. Git и image context игнорируют token files.
- Восемь demo fixtures, повторяемый seed через реальный authenticated HTTP endpoint,
  Compose smoke helper и его запуск в CI. Интерфейс отражает прогресс Этапа 2.

## Проверки

- Backend: 81 pytest tests; Ruff check/format, mypy strict (23 source files).
- Миграции: empty/idempotent/roundtrip, сохранение посторонней таблицы, metadata diff
  (`alembic check`) и наличие индексов.
- Auth/security: missing/wrong/revoked credentials, duplicate auth headers,
  host/kind spoofing, secret redaction, JSON/size/port/time/IP validation,
  IPv6 zones/mapped addresses, malformed input, duplicate JSON keys, NaN/Infinity.
- Storage: concurrent duplicates, отсутствующий stable ID, scope source ID,
  first-payload-wins, rollback с DB CHECK failure без частичных side effects,
  writer backpressure и восстановление, rollups на hour/UTC offset boundaries.
- Read API: AND filters, half-open ranges, UUID detail, stable timestamp ties,
  late-delivery snapshot, changed/invalid/expired cursor, bounded page/sort,
  SQL injection input и cross-origin rejection.
- Limits: chunked body, early oversized array rejection, body timeout,
  token bucket refill/source isolation, source/global concurrency и release permits.
- CLI: token mode 0600, directory mode 0700, digest-only DB, no overwrite/symlink,
  rollback при неизвестном host, отсутствие секрета в CLI stdout/stderr.
- Настоящие subprocess listeners/SIGTERM и HTTP demo roundtrip/retry.
- HTTPX2 2.16.0 заменил deprecated HTTPX transport; прежнее предупреждение исчезло.
- Frontend: 6 Vitest tests, ESLint, Prettier, strict TypeScript и production build.
- Docker Compose config, production build, Nginx config check, оба healthchecks,
  Compose smoke (8 observations, repeat=8 duplicates, read API и redaction).
- Windows localhost:8180: HTTP UI, JS/CSS, readiness, hosts/events/detail проверены.
  В локальной базе 16 observations (два demo run_name), sum(hour counts)=16,
  pending work=16. EXPLAIN использует covering index ix_events_src_ip_time_id.

## Локальная база

Перед добавочной миграцией создана SQLite backup API копия
`/data/backups/before-stage2.db` в том же persistent volume. Старый revision —
0001_baseline, новый — 0002_event_storage. Исходные domain tables отсутствовали;
данные не удалялись. Тестовые migration downgrade выполнялись только на временных DB.
Токены и demo manifest хранятся только в local volume, в Git их нет.
Автоматическое резервное копирование для установки пользователя пока не реализовано.

## Как проверить

```bash
docker compose up --build --wait
docker compose exec -T backend python -m attackscope.demo
docker compose exec -T backend python -m attackscope.demo
```

Первый запуск нового run_name принимает 8 events, повторный — 8 duplicates.
В JSON есть events_path: открыть http://localhost:8180 + этот путь.
Список хостов: http://localhost:8180/api/v1/hosts.

```bash
docker compose -f deploy/compose.test.yaml build --parallel
docker compose -f deploy/compose.test.yaml run --rm backend-test
docker compose -f deploy/compose.test.yaml run --rm frontend-test
python3 tests/compose_smoke.py
```

Точная регистрация источников, fields, filters и ограничения — [INGESTION.md](INGESTION.md).

## Исправления во время проверки

Первичная Nginx regex location с `{36}` требовала кавычек: configuration test выявил
ошибку, regex исправлен, после этого Compose smoke прошёл. Ранние lint ошибки
imports/format устранены. При security review проверка размера массива перенесена
до item validation, а неожиданные exceptions перехватываются без передачи исходного
текста в Uvicorn traceback. Эти случаи покрыты tests. Нет незавершённых test failures.

## Ограничения и риски

- Реальные journald/Nginx/firewall парсеры, Vector и внешний TLS listener — Этап 4.
- Timeline остаётся макетом, Event Explorer/IP Explorer/Overview ещё не реализованы.
- Classification/findings consumer pending_events — Этап 5. Пока queue накапливается.
- Retention ограничивает приём и чтение, physical cleanup/historical queries — Этап 8.
- Без source_reference нет гарантии dedup; после dedup horizon повтор допускается.
- Токен администратора источника не делает данные достоверными: скомпрометированный
  источник может отправлять ложные наблюдения своего host/kind в пределах лимитов.
- Секреты в path segments/UA/username автоматически не распознаются; source logging
  должен быть безопасным. Произвольные raw logs не сохраняются.
- Cursor не подписан, предназначен только для позиции в локальном read API, не auth.
- Rate limits in-memory, после restart бюджет восстанавливается; transport Uvicorn
  может вернуть свой 503 до application error envelope.
- Нагрузочных измерений и browser rendering tests не проводилось. HTTP из Windows
  проверяет доступность, не выполнение JS в настоящем браузере.
- CI workflow подготовлен и эквивалентные команды проверены локально; push/GitHub CI
  execution не выполнялись. Полный license/vulnerability audit — до release.

## Следующий этап

Timeline MVP: server aggregation по диапазону и бюджету точек, три lanes,
zoom/pan/presets/custom range, host/IP filters, details, loading/empty/error states.
Начинать после согласования плана Этапа 3.

## Официальные источники

[SQLAlchemy SQLite upsert](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#insert-on-conflict-upsert),
[Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/),
[Starlette request streaming](https://starlette.dev/requests/),
[Starlette TestClient и HTTPX2](https://starlette.dev/testclient/).

## Файлы и сохранённое состояние

Изменены backend API/config/storage/server, добавлены normalization, response schemas,
CLI/demo, миграция и tests. Добавлены fixtures/events.json и tests/compose_smoke.py;
обновлены Nginx read routes, Compose/env limits, CI, ignore files, README и docs.
Frontend изменён только в подписях прогресса; функциональную Timeline не добавляли.
Контейнеры оставлены работающими на localhost:8180, remote и push отсутствуют.
