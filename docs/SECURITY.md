# Модель безопасности v0.1

UI/read API предназначены для localhost и одного доверенного оператора. По
умолчанию публикуется только 127.0.0.1:8180, backend не публикуется. Nginx Host
allowlist и read Origin checks снижают риск DNS rebinding; это не multi-user auth.
Не открывайте UI в Интернет до отдельной аутентификации и TLS reverse proxy.
Ingestion — другой listener, индивидуальные 256-bit source tokens, hash в DB,
constant-time comparison, host/kind назначаются authenticated identity.
VPN без source credentials недостаточен. Для настоящего агента нужен HTTPS
с проверкой сертификата либо защищённый туннель плюс source auth.

Обрабатываются недоверенные поля, а не команды. Parameterized SQL, allowlisted
sort, bounds для time/IP/ports/fields, RFC3339 UTC, canonical IPv6. Max request
1MiB/500 events, no compressed ingestion, body timeout; global/source/write/pool
limits. Validation errors не возвращают входные поля/секреты; operational logs
не пишут payload/token/SQL params. Raw journal message discarded; HTTP query
values/Authorization/Cookie/body не сохраняются. В пути/UA/username могут быть
чувствительные значения: не отправляйте секреты в URL path и display fields.

React text nodes; ECharts canvas richText tooltip; нет dangerous HTML вставки.
CSP script-src self/object-src none/frame-ancestors none, no CORS wildcard.
CSV formula escaping, quoted cells и bounded atomic export. Replay stable IDs
проверяется в одной write transaction; без stable ID dedup не гарантируется.
Cursor — position token, не credential; filters fingerprint, expiry, SQL bounds.

Контейнеры non-root, read-only rootfs, tmpfs, cap_drop ALL, no-new-privileges,
pids/memory limits. Docker socket не монтируется, privileged отсутствует.
Browser/Vector checks запускаются отдельными test containers, не в runtime.
SQLite WAL patched runtime, indexes/FKs, query deadlines, rollback и backup API.
Retention eventual и query cutoff не раскрывают expired detail через read API.

Проверены auth/spoof/replay/concurrent retry, oversized/invalid/bounded input,
redaction/XSS render/CSV injection, migration/rollback/retention, real Chromium
navigation/download/mobile и Vector HTTP encoding. Не проводился независимый
pentest. TLS/journald реальной VM не проверялись. Production dependency npm audit
вернул 0 известных уязвимостей на момент проверки; полный dev audit выявил minimatch DoS в lint dependencies.
Исправление pinned override 11.0.1 проверяется lint/types/tests; информация
upstream: https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249.

Сообщения о проблемах: до публикации репозитория используйте локальный issue
или приватный канал владельцу. Не размещайте source tokens и реальные логи
в публичных issues. Внешний репозиторий и security contact ещё не опубликованы.
