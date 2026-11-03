> Исторический отчёт первоначальной локальной приёмки. Текущий исходный код и проверки первой публикации описаны в [ROADMAP.md](ROADMAP.md) и [PUBLICATION.md](PUBLICATION.md). Показатели ниже относятся к тому прогону, а не к последней версии.

# AttackScope v0.1: локальный итог

Приложение завершено в согласованном MVP scope и оставлено на
**http://localhost:8180**. Основной запуск — два non-root Docker контейнера.
Есть Timeline, IP Explorer, Overview, Event Explorer/экспорт, отдельная историческая
страница, правила, ingestion/auth/dedup, Vector examples, retention и backup.
Никакой внешней публикации, push или подключения настоящих VM не выполнялось.

## Проверка утром

1. Откройте localhost8180, выберите24h и VM **demo-morning**:2086 синтетических
   наблюдений, отдельные8-event тестовые VM также сохранены и видны без host filter.
2. Нажмите HTTP кластер →«Исследовать интервал», приближайте до отдельных событий.
   Кружки — наблюдения, ромбы — результаты правил. Наведите для точного count.
3. Найдите198.51.100.77 (web scanning),203.0.113.42 (SSH) или2001:db8::bad (ports).
   Откройте finding: threshold,observed,count,window и evidence IDs.
4. Перейдите к IP Explorer, посмотрите VM/порты/paths/status/SSH outcomes/часы.
   «Все события этого IP» сохраняет диапазон и IP filter в Event Explorer.
5. Отсортируйте таблицу, переключите страницы, откройте safe projection,
   скачайте CSV/JSON с выбранными filters.
6. Overview: все HTTP отдельно от подозрительных. «История до365d» — полные UTC
   часы с явным effective range, без выдуманных старых detail fields.

Для свежего demo: новый run-name в команде ниже. Существующий morning повторяет
только duplicates; не создаёт заново timestamps и не удаляет данные.

```sh
docker compose exec backend python -m attackscope.demo --run-name fresh-demo --scenario investigation
```

## Выполненные проверки

- Backend: **111 pytest**, Ruff lint/format, strict mypy (34 modules).
  Включены API/auth/spoof/limits, parsers, duplicates/concurrency/rollback,
  classification/late delivery/cache, time/buckets, migrations/indexes, retention,
  filtered exports/formula injection, private backup→isolated restore.
- Frontend: **7 Vitest**, ESLint, Prettier, strict TypeScript, production Vite build.
  Проверки XSS text rendering и pending/error/retry. Bundle warning >500kB
  (около273kB gzip) остаётся видимым, не маскируется настройкой порога.
- Настоящий Chromium: Timeline/zoom/cluster drill, event pagination, safe card→IP,
  IP→filtered events, historical view, Overview, JSON download, mobile viewport;
  без page errors. Скрипт tests/browser_smoke.py.
- Compose build/up/healthy, read/injection isolation, Host rejection, demo replay,
  Nginx config test. Runtime оставлен работающим.
- Три Vector0.61 config прошли validate; настоящий stdin→transform→HTTP JSON array
  smoke подтвердил auth header, duration conversion и удаление query/extra secrets.
- Optional TLS proxy: локальный временный certificate, проверка chain+hostname,
  authenticated duplicate=1, unauthorized401. System trust store не менялся,
  тестовый sidecar после проверки остановлен и удалён. tests/tls_smoke.py.
- Npm production и полный audit после minimatch11.0.1 override:0 known vulnerabilities
  на момент проверки. Hash locks и runtime license notices сохранены.
- Benchmark10k/100k: throughput674/770 events/s, p95 Timeline94/359ms,
  process RSS78/79MiB; SQL IP/time использует covering index. Это WSL-стенд,
  не SLA VPS. Полный метод и ограничения — PERFORMANCE.md.
- Backup CLI создал /data/backups/release-0.1.db, integrity/FK проверены.
  Restore протестирован в новой изолированной DB, рабочая не перезаписывалась.

GitHub Actions расширен этими checks, но реального запуска на GitHub не было.
Windows curl повторно не запустился в текущем sandbox из-за WSL vsock restriction;
доступ проверен Linux Chromium/HTTP. Ранее Windows forwarding8180 был проверен,
порт/binding с того момента не менялся. Это не результат Windows browser test.

## Что изменено

backend: typed normalization/adapters, bounded timeline/analytics/history/export,
classification worker и findings migration, retention/indexes/cache, backup CLI.
frontend: все страницы/связи/filter forms, ECharts adaptive groups/findings,
safe detail/export и license notices. deploy: TLS/Vector/log examples, Docker
limits и test images. docs: PRD/архитектура/data/API/ADR/roadmap, установка,
collection, безопасность, операции/backup, troubleshooting и release checklist.
Лицензия проекта пока не выбрана; secrets/DB/logs не входят в публикацию.

## Ограничения и риски

- Реальная VM отсутствовала. Локальные adapter/Vector/TLS checks не заменяют
  journald и доставку с настоящего сервера; этот внешний критерий не выполнен.
- Single-operator localhost UI без multi-user login. Внешний UI deployment
  не выполнен; не открывайте его в Интернет без отдельной auth/TLS схемы.
- Fixed UTC windows могут пропустить активность на стыке. SSH считает записи,
  не уникальные login sessions; логирование firewall неполное/rate-limited.
  Findings не доказывают успешную атаку. GeoIP/ASN — unavailable.
- Vector memory buffer теряется при crash; без stable source ID нет гарантии
  dedup. After TTL replay не гарантирован. Evidence ограничены100 links.
- 1M, full classifier throughput, длительный soak и independent pentest не
  проверялись. Большие uncached aggregates могут дать503deadline; используйте
  более узкий range/IP/host или historical rollups. Полный OS SBOM не выполнялся.
- Cleanup eventual, SQLite pages переиспользуются, file не обязательно уменьшается.
  URL/status/outcomes доступны30d, historical только полные часы до365d.

## Release checklist

- [x] Local Compose quickstart и demo
- [x] Основные страницы и filtered export
- [x] Auth/redaction/idempotency/classification
- [x] Unit/integration/migration/security/retention checks
- [x] Chromium/Vector/local TLS checks
- [x] Backup и изолированный restore test
- [x] 10k/100k measurements и документированные границы
- [x] License/notices/install/update/troubleshooting/CI config
- [ ] Настоящая test VM (не предоставлена)
- [ ] GitHub CI execution/external publication (не запрашивались)

Следующие этапы MVP не требуются. Дальнейшая работа — операторская проверка VM
и исправление найденных при использовании ошибок. v0.2 функции не начинались.
