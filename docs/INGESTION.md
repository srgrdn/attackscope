# Приём событий и работа с API — Этап 2

## Быстрая проверка без VM

```bash
docker compose up --build --wait
docker compose exec -T backend python -m attackscope.demo
```

Demo создаёт отдельный хост и три источника с разными случайными секретами, берёт
восемь безопасных структурированных событий из `fixtures/events.json`, подставляет
UTC-время и отправляет в ingestion через HTTP внутри backend container.
В JSON-ответе: accepted, duplicates, host_id, query и events_path. Откройте
`http://localhost:8180` + events_path для просмотра сохранённых событий.
Повторите команду: ожидаются accepted=0, duplicates=8.

Токены demo находятся в `/data/demo/default/*.token`, mode 0600; каталог mode 0700.
Manifest не содержит секретов. Время первой генерации сохраняется для повторной
доставки; если demo старше detail retention, используйте новый `--run-name sample2`.
Повтор одного run_name использует тот же хост и исходные ID. Параллельный запуск
одного run_name не поддерживается; запускайте seed последовательно.

Команда создаёт наблюдения, но не утверждает, что это атаки. HTTP 404 остаётся
info, classification=null. Реальные journald/Nginx/nftables парсеры появятся на Этапе 4.

## Регистрация локального источника

```bash
docker compose exec -T backend python -m attackscope.cli create-host --name vm-01
```

Из ответа взять host_id и создать источник нужного kind:

```bash
docker compose exec -T backend python -m attackscope.cli create-source \
  --host-id HOST_UUID --kind http --token-file /data/secrets/vm-01-http.token
```

Kinds: http, ssh, firewall. Каждый source допускает один kind и один immutable host.
Секрет генерируется криптографически, не передаётся аргументом CLI и не выводится
в stdout. CLI печатает только IDs и путь. В БД хранится SHA-256 digest полного
токена; random secret содержит 256 бит энтропии. Constant-time digest comparison.
Файл создаётся исключительно новым с mode 0600, существующий файл/symlink не
перезаписывается. Передача секрета на VM — отдельная операторская процедура Этапа 4.
Не добавлять token files в Git, не вставлять токен в URL, shell history или журналы.

Отключить скомпрометированный источник:

```bash
docker compose exec -T backend python -m attackscope.cli disable-source --source-id SOURCE_UUID
```

Для замены создать новый источник с новым секретом и отключить старый. Смена source ID
меняет namespace дедупликации: события из двух источников могут сохраниться повторно.
Публичного provisioning/admin write API нет.

## Транспорт

Ingestion `POST /api/v1/ingest/events` доступен на внутреннем backend:8001.
Host port не опубликован; UI proxy не пропускает этот маршрут. HTTP внутри локальной
Docker network используется для demo, внешний ingress в MVP потребует TLS и source
credentials. Не публиковать текущий listener напрямую в интернет.

Authorization: `Bearer <source_uuid>.<random_secret>` — из private token file.
Body: JSON array 1..500 envelopes, Content-Type application/json, UTF-8.
Raw log lines не принимаются. Формат примера без credentials:

```json
[{
  "transport_version": 1,
  "schema_version": 1,
  "source": "http",
  "source_reference": "access.log:generation:offset",
  "payload": {
    "timestamp": "2026-11-03T00:00:00Z",
    "remote_addr": "2001:db8::10",
    "request_method": "GET",
    "path": "/.env?token=discarded",
    "status": 404,
    "dst_port": 443,
    "duration_ms": 12.5
  }
}]
```

Время примера заменить на текущее. Допустимо окно от текущего detail cutoff (30 дней,
вниз до начала UTC часа) до now+5m. Timezone обязательна; RFC3339 fractions до 9 цифр,
хранение с точностью microseconds. Epoch numbers/naive time отвергаются.

Payload http: timestamp, remote_addr, request_method, path, status обязательны;
user_agent, duration_ms, dst_ip, src_port/dst_port, protocol необязательны.
Payload ssh: timestamp и outcome (success/failure/invalid_user/disconnect), nullable
src_ip/dst_ip/ports/protocol/username. Payload firewall: timestamp, nullable IP/ports/
protocol/action (accept/drop/reject)/interface. Неизвестное действие не угадывается.
Protocols: tcp/udp/icmp/icmpv6/http/https, lowercase. IPv6 zones не поддерживаются;
IPv4-mapped IPv6 сводится к IPv4. Unknown payload fields отбрасываются.
Unknown envelope fields — 422, чтобы не скрывать ошибку transport contract.

Если передан envelope.host_id, он должен совпасть с authenticated source: иначе 403.
Payload hostname/host_id не определяют принадлежность события. ID, received_at,
category, event_type, severity и classification задаёт backend.

## Безопасное сохранение

Убираются query и fragment целиком. Authorization, Cookie, body, произвольные
headers и journald MESSAGE не входят в allowlist и не сохраняются. `safe_original`
— только безопасная проекция распознанных полей, а не исходная сырая строка.
Path <=2048 UTF-8 bytes, UA <=512, username <=128, interface <=64; управляющие
символы удаляются, усечённые display fields отмечаются в attributes.sanitized_fields.
Path превышенного размера отклоняется. JSON projections ограничены DB CHECK 8 KiB.
Секрет, встроенный в сам path или свободный текст UA/username, нельзя гарантированно
распознать: источник обязан выбирать безопасный log format. Дополнительные правила
redaction для path segments пока не реализованы.

## Повторная доставка

Успешный ответ 200 только после commit: accepted, duplicates, schema_version.
Вся партия атомарна: один некорректный элемент => 422 и ни одного нового события.
Events, delivery keys, pending work и hourly counters записываются в одной транзакции.
Duplicate не увеличивает счётчики и очередь. Одинаковый ID с изменённым payload
не заменяет событие: первый commit выигрывает, ответ учитывает duplicate.

source_reference — стабильный opaque ID, ASCII letters/digits/:._/- до 512 bytes.
Для journald cursor с символами `=`/`;` понадобится encoding в адаптере Этапа 4.
Namespace — source UUID; источник должен включать stream identity/rotation generation.
Без source_reference одинаковые записи сохраняются отдельно. Content hash не
используется, чтобы не терять реальные одинаковые наблюдения. Dedup horizon по
умолчанию 30 дней от получения; expired key заменяется при следующей доставке.
Фоновая очистка остальных expired keys относится к Этапу 8.

## Лимиты и ошибки

.env.example содержит defaults: body 1 MiB до parsing, batch 500 до item validation,
16 global API slots, 2 concurrent/source, 5 req/s/source, burst 10; 5s body timeout,
5s SQLite busy timeout и query progress deadline. Нет неограниченной writer queue.
Rate state хранится в памяти и сбрасывается при restart; auth/revocation/dedup — в DB.
Compressed input, NaN/Infinity и duplicate JSON keys не принимаются.

401 — auth, 403 — source/host mismatch, 408 — body timeout, 413 — size,
415 — content type/encoding, 422 — invalid data, 429 — source limits,
503 — writer/global/pool/DB unavailable. Application 429/503 включают Retry-After.
Дополнительный transport limit Uvicorn может вернуть обычный 503 до входа в app.
Ошибки приложения содержат code/message/request_id без input, SQL и secrets;
неожиданные ошибки логируются только по class и request_id без exception message.

## Чтение

UI base: http://localhost:8180/api/v1.
GET /hosts — limit=100 (max500), cursor UUID.
GET /events — обязательные from/to, полуоткрытый UTC range [from,to), max 30d default.
Фильтры: host_id, ip (src), source, category, port (destination), severity.
Categories: ssh_authentication/ssh_connection/http_request/firewall_packet.
Sort: sort=timestamp, order=desc/asc; default limit100, max500. Следующие страницы
повторяют filters/from/to/order и передают next_cursor. Внутри tie-breaker event UUID.
Cursor живёт 15m; смена фильтров — 422, expiry/недоступная detail history — 410.
Cursor — валидируемая позиция, не secret/auth token; не подписан и не даёт privileges.
Received-at watermark фиксирует snapshot; события, принятые позже первой страницы,
появятся только после начала нового запроса. exact total на каждой странице не считается.
GET /events/{uuid} — карточка, безопасная проекция и attributes, 404 вне retained detail.
UI пока не имеет таблицы событий: это JSON API для следующего этапа Timeline.

Сейчас retention ограничивает приём и чтение; физическая очистка и исторические
aggregate queries — Этап 8. Findings и классификация — Этап 5. Нагрузочные пределы
ещё не измерены, API caps не являются обещанием throughput.
