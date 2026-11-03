# Архитектурные решения

Архитектурные решения v0.1. Выбор лицензии самого проекта отложен.
Изменение решения требует описания
причины, миграционных последствий и обновления связанных документов.

| ADR | Решение | Альтернативы / компромиссы |
|---|---|---|
| 001 | Modular monolith backend, React отдельно | Microservices/queues сложнее эксплуатационно; монолит ограничивает горизонтальное масштабирование |
| 002 | SQLite WAL, local persistent volume, один worker | PostgreSQL лучше concurrent writes, но добавляет сервис; переход только по измеренным пределам |
| 003 | Docker Compose основной runtime | Host install проще некоторым операторам, но хуже воспроизводимость; Docker daemon/Compose обязательны |
| 004 | Два listener/app внутри backend lifecycle | Один app с proxy denylist проще, но рискует открыть admin route; отдельный ingestion контейнер добавляет сервис и координацию writers |
| 005 | Individual source tokens + TLS + host binding | VPN-only не защищает от подмены агента; mTLS сложнее provisioning и отложен |
| 006 | Safe source projection вместо полного raw log | Полный raw полезнее для forensic, но содержит secrets/PII; неизвестные поля теряются намеренно |
| 007 | At-least-once + stable source reference | Content hash может удалить реальные одинаковые события; exactly-once transport не обещается |
| 008 | Immutable observations + separate findings | Переписывание events теряет исходные свидетельства; summary classification eventual и производная |
| 009 | Серверные buckets и detail по бюджету точек | Только client aggregation перегружает браузер/сеть; сервер требует фильтров и boundary tests |
| 010 | UTC microseconds DB, RFC3339 API, half-open ranges | SQLite naive DATETIME неоднозначен; integer менее удобен для ручного SQL, зато точен |
| 011 | Hourly rollups по IP/host/category/source/port | Полные URL/status dimensions слишком cardinal; marginal rollups теряют совместные фильтры; выбранный вариант тоже требует disk benchmark |
| 012 | Durable work в SQLite, bounded maintenance | In-memory queue теряет работу при crash; Celery/Redis избыточны; DB job state усложняет транзакции |
| 013 | Локальный UI без remote auth в MVP | Remote UI с password/session требует отдельного threat model; localhost не оправдывает публикацию наружу |
| 014 | Без GeoIP provider по умолчанию | Онлайн API раскрывает запросы, local DB требует лицензии/обновлений; интерфейс возвращает unavailable |
| 015 | Fixed rule bucket identity и rolling event windows | Чистый per-event finding создаёт шум; incident merging сложнее. На границе buckets возможны несколько findings одной серии, это не отдельные атаки |
| 016 | Лицензия проекта пока не выбрана | Решение отложено; лицензии и уведомления сторонних компонентов сохраняются |

## Условия пересмотра

- Блокировки SQLite/ingestion lag после индексов и batching: оценить PostgreSQL,
  не добавлять внешние очереди автоматически.
- Rollup disk growth превышает бюджет: измерить, согласовать более короткий retention
  или потерю определённых historical filters, не скрывать approximation.
- Необходим remote UI: отдельно согласовать TLS, session/auth, CSRF, password handling.
- Новый источник: versioned adapter + fixtures + safe allowlist; ядро и event schema
  меняются только при невозможности выразить нужные данные через существующие contracts.
- Новые thresholds/rules: version и snapshot обязательны, historical results не
  переписываются незаметно; reclassification — явная отдельная операция.

## Риски до реализации

Dependency lockfiles и Docker digests каркаса проверены на Этапе 1 (STAGE_1.md).
Vector batching, stable IDs,
journald permissions и retry permanent failures необходимо подтвердить интеграционно.
Нет тестовой VM в согласованном scope: критерий Этапа 4 с реальными событиями
нельзя объявить выполненным только по fixtures. Нет измерений throughput/memory/disk.
Non-root, read-only rootfs, volume access и lifecycle двух listeners проверены
на Этапе 1. Пропускная способность ingestion пока не измерялась.

## Уточнения Этапа 2

- Подтверждены atomic events/dedup/rollups/pending records и writer BEGIN IMMEDIATE.
- Cursor snapshots используют монотонный received_at + индекс, без отдельной batch table.
  Cursor не подписан: read API локальный и не разграничивает доступ; позиция и filters
  валидируются, SQL всегда parameterized. При remote auth это решение пересмотреть.
- Structured JSON adapters — Этап 2, text log parsers/Vector — Этап 4. Это позволяет
  проверить storage/API без преждевременного доступа к VM.
- TestClient переведён на HTTPX2 2.16.0 по актуальной документации Starlette;
  runtime dependencies backend не изменились.

## ADR: воспроизводимые fixed UTC окна v0.1

Решение этапа 5: классификатор использует фиксированные UTC окна, durable pending
в SQLite и deterministic finding IDs (rule/version/host/IP/window/config).
Rolling windows требуют пересчёта большего числа окон при late delivery; они
точнее на стыке, но сложнее и дороже. Для MVP выбран fixed вариант, возможный
пропуск на границе явно описан в CLASSIFICATION.md. Нет внешней очереди/worker
сервиса. До 100 evidence IDs, фактическое count не обрезается.

## ADR: historical coverage и границы нагрузки

MVP history считает полные UTC часы с явными effective_from/to. Пропорциональная
оценка частичных bucket дала бы вымышленные counts, поэтому исключена. Detail
и aggregates не суммируются в одной метрике; top lists имеют truncation.
Нагрузка проверена на10k/100k, 1M и full classification throughput не заявляются.
Дополнительные indexes для retention FK и classifier введены migration0004.
Оператор может воспроизвести benchmark в отдельной временной DB.

## ADR: простой release без внешней публикации

Версия приложения0.1.0. Лицензия проекта пока не выбрана; публикация исходников
не меняет лицензии сторонних компонентов.
UI single-operator localhost, optional TLS proxy публикует только authenticated
ingestion path; login/multi-tenancy вне MVP. Browser test image отдельный и не
входит в runtime. Backup API exclusive create, restore проверен в изолированной
DB; команда перезаписи рабочих данных не добавляется.

## ADR: одна рабочая VM, закрытая сеть и восстановление

Production отдельно от demo: новый Compose project/volume, прежняя база сохранена.
UI остаётся за SSH и Unix socket. Vector в internal Docker network с отдельными
source tokens; HTTP между контейнерами одной VM, HTTPS обязателен для внешних VM.
File secret provider исключает tokens из Docker environment. До disk buffer
остаётся только нормализованный allowlist; checkpoint/ACK и стабильные IDs дают
восстановление с идемпотентной записью. Два buffer по256МиБ — минимальный размер
Vector disk buffers; это дисковый расход, не резерв памяти. Другие очереди не нужны.

Crash test выявил смену backend IP и stale UI upstream. В Nginx1.30.6 выбран
shared upstream с resolve и trusted Docker DNS, без привязки к конкретному IP
и без необходимости перезапуска UI при смене endpoint. Regression test воспроизводит
замену backend на другой IP. Readiness/allowlist/security headers сохранены.

Maintenance — root-owned host helper с systemd restrictions и сериализацией;
runtime-контейнеры без Docker socket. Backups включают DB, private source credentials
и image metadata. Restore идёт только в новую временную БД с проверкой credentials.
Offsite backup и уведомления требуют заданного оператором назначения; не имитируются.

## ADR: расширенные sensitive paths и недоверенная пометка проверок

Наблюдаемые cloud/container credential probes не покрывались исходным коротким
списком. Выбран расширенный точный allowlist путей sensitive_path v2 с bounded
matched_paths в evidence. Подстроки и широкие regex дали бы ложные срабатывания
на документации/обычных URL; автоматическое снижение rate thresholds не требуется.
Версия входит в finding ID, прежние записи сохраняются. Миграции и массового
пересчёта старых журналов не добавляется.

Операторские проверки получают только UI hint по известным User-Agent. Альтернатива
автоматического исключения таких запросов дала бы атакующему простой обход правил.
Криптографически подтверждённые markers потребовали бы отдельной доставки секретов
и изменения producers; для этой задачи это лишняя сложность. Поэтому подсказка
явно обозначена как неподтверждённая и не меняет анализ/хранение/экспорт.
