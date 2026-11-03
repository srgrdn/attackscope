# AttackScope — требования v0.1

Статус: MVP v0.1 реализован. Текущее состояние и ограничения — в ROADMAP.md;
ниже зафиксированы функциональные и нефункциональные требования.

## Продукт и пользователь

Self-hosted платформа наблюдения за подозрительной сетевой активностью нескольких
Linux VM. Главная ценность — интерактивная Event Timeline: когда, с какого IP,
на какой сервер и к какому ресурсу наблюдалось обращение. Хранится свидетельство,
а не утверждение о полном охвате трафика или успешной атаке.

## Обязательные сценарии

| ID | Требование | Проверка готовности |
|---|---|---|
| F01 | SSH из journald: success, failure, invalid user, disconnect | Парсеры на позитивных, неизвестных и испорченных строках |
| F02 | Nginx JSON: время, IP, host, method, path, status, UA, nullable port/duration | IPv4/IPv6, безопасная проекция без query values и заголовков |
| F03 | Firewall journald nftables/iptables | Извлечение известных полей; неизвестные остаются null, action не угадывается |
| F04 | Нормализованные versioned events и batch ingestion | Auth, host binding, retry, атомарность и duplicate tests |
| F05 | Timeline с SSH/HTTP/Firewall дорожками | Zoom, pan, presets 1h/24h/7d/30d, custom range, host/IP/category/port filters |
| F06 | Timeline detail/aggregate modes | Сервер выбирает масштаб, реальные counts, bounded payload, drill-down |
| F07 | Explainable rules | SSH brute force, web scanning, sensitive paths, port probing; настраиваемые пороги |
| F08 | IP Explorer | First/last, counts/types/hosts/ports/paths/status/auth, история и findings |
| F09 | Overview | Events, unique IP, suspicious sources, categories, top IP/path/port, time series |
| F10 | Event Explorer | Time/IP/host/source/category, sort, cursor pages, details, CSV/JSON export |
| F11 | Исторические агрегаты и retention | 30 дней detail, до 365 дней rollups; явное обозначение доступности данных |
| F12 | Воспроизводимое demo без VM | Детерминированные fixtures, IPv6, empty и dense scenarios |

Число HTTP requests отображается отдельно от suspicious events и findings.
Event — наблюдение; finding — результат правила по одному или нескольким событиям.
Одно событие может участвовать в нескольких findings и считается в общем числе один раз.
Недоступные GeoIP/ASN обозначаются как недоступные; геоданные относятся к IP, не личности.

## Нефункциональные требования

- Основной запуск через Docker Compose, без обязательного host Python/Node.
- Небольшой VPS; расход RAM/CPU/disk измеряется воспроизводимым benchmark,
  численные обещания до измерений не даются.
- UTC внутри системы, IPv4/IPv6, ограниченные запросы/поля/батчи/экспорт.
- SQLite WAL на локальном filesystem, миграции, пакетные транзакции, индексы.
- Read-only наблюдение: никаких блокировок и изменений правил на VM.
- TLS для внешнего ingestion и отдельная аутентификация каждого источника.
- UI/admin по умолчанию доступны только через localhost; секретов нет в Git.
- Dark responsive UI, понятные loading/empty/error states, tooltips и клавиатурные controls.
- Unit/integration/parser/classification/aggregation/migration/security tests, strict TS,
  Ruff, pytest, Vitest, CI; mypy при введении backend contracts.
- Зависимости с совместимыми открытыми лицензиями; проверка прямых и транзитивных
  лицензий при фиксации версий. Лицензия самого проекта пока не выбрана;
  сторонние уведомления сохраняются отдельно.

## Вне MVP

CPU/RAM/disk monitoring, SIEM, IDS/IPS, auto blocking, LLM, Kubernetes,
Elasticsearch, Kafka, Redis/Celery; GeoIP provider implementation, reputation,
CrowdSec/Suricata/WAF integrations и карты. Для enrichment предусмотрен интерфейс.

## Ограничения наблюдения

Firewall содержит только реально залогированные пакеты; rate limit создаёт пробелы.
Отсутствие событий не доказывает отсутствие активности. 404 не равен атаке;
SQLi/XSS строки не доказывают эксплуатацию. После retention нет точной детализации,
URL/status/auth history за удалённый период недоступны. Точные distinct IP сохраняются
в пределах хранимых IP rollups; значения нельзя суммировать как независимые counts.
