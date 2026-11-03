# AttackScope v0.1

Лёгкая self-hosted платформа для истории подозрительной сетевой активности Linux.
Главный экран — Timeline с дорожками SSH, HTTP и Firewall: исследуйте всплеск,
откройте наблюдения, перейдите к IP и выгрузите выбранный диапазон.

Весь основной запуск — **Docker Compose**: FastAPI + SQLite WAL и React/Nginx.
Обязательных облачных сервисов нет. Приложение ничего не блокирует и не меняет
SSH, firewall или Nginx ваших серверов. Лицензия проекта пока не выбрана;
уведомления сторонних компонентов сохранены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Быстрый запуск

Нужны Docker Engine и Compose v2. Подробности: [установка](docs/INSTALLATION.md).

```sh
git clone https://github.com/srgrdn/attackscope.git
cd attackscope
docker compose up --build --wait
docker compose exec backend python -m attackscope.demo --run-name morning --scenario investigation
```

Откройте **http://localhost:8180**. Порт привязан только к localhost.
Demo содержит 2086 синтетических наблюдений с адресами документации; запросов
к реальным целям не делает. Повтор команды с тем же run-name не дублирует записи.
Классификация фоновая: подождите около минуты после первой загрузки.
Другой run-name создаёт отдельную demo VM; его используйте для свежего набора.

Конфигурация по умолчанию работает без `.env`. При необходимости скопируйте
`.env.example` в новый `.env`, не перезаписывая уже настроенный файл.
Из host Python/Node ничего устанавливать не нужно.

## Возможности

- Timeline: отдельные наблюдения или точные серверные группы, zoom/pan/cluster
  drill-down, 1h/24h/7d/30d и произвольный UTC диапазон, VM/IP/category/port filters.
- IP Explorer: типы событий, VM, порты, URL, HTTP-статусы, SSH outcomes, история,
  first/last в сохранённых данных и объяснимые findings. GeoIP/ASN — unavailable
  без базы; внешних запросов к сервисам репутации нет.
- Overview: общая активность отдельно от подозрительных HTTP/events/IP.
- Event Explorer: фильтры, сортировка, keyset pages, safe detail, CSV/JSON export.
- История до 365d: hourly rollups по IP, времени, host, category и port.
  После 30d детали URL/status/raw projection недоступны; полные часы явно указаны.
- Правила SSH brute-force, web rate/distinct paths, sensitive paths, observed port
  probing; thresholds настраиваются, причины и evidence доступны в карточке.
- Source auth с привязкой host/kind, idempotency, bounded input/queries, retention,
  миграции, private backup, безопасные примеры Vector SSH/Nginx/firewall.

Успешный HTTP 404 не называется атакой автоматически. Finding — объяснимая оценка
наблюдаемой активности, не доказательство успеха атаки или личности источника.
Нет LLM, автоблокировок, CPU/RAM мониторинга, Elasticsearch/Kafka/Kubernetes.

## Документация

- **[Подробное руководство со скриншотами](docs/USER_GUIDE.md)**
- **[Вики: экраны, расследования, эксплуатация и справочник](docs/wiki/README.md)**
- [Утренняя проверка и ограничения](docs/RELEASE_0_1.md)
- [Установка](docs/INSTALLATION.md), [сбор с Linux / Vector](docs/COLLECTION.md)
- [Закрытый deployment на VM через SSH](docs/VM_DEPLOYMENT.md)
- [Пример закрытой установки с Vector и обслуживанием](docs/PRODUCTION.md)
- [Источники, CLI и токены](docs/INGESTION.md)
- [Обновление и backup/restore](docs/OPERATIONS.md), [troubleshooting](docs/TROUBLESHOOTING.md)
- [Классификация](docs/CLASSIFICATION.md), [IP Explorer](docs/IP_EXPLORER.md)
- [Overview / экспорт](docs/EXPLORERS.md), [retention / история](docs/RETENTION.md)
- [Безопасность](docs/SECURITY.md), [измерения нагрузки](docs/PERFORMANCE.md)
- [Архитектура](docs/ARCHITECTURE.md), [модель](docs/DATA_MODEL.md), [API](docs/API.md)
- [Roadmap / состояние](docs/ROADMAP.md), [решения](docs/DECISIONS.md)

Для своей VM настройте Vector и отдельные authenticated sources. Примеры
развёртывания требуют проверки путей, UID/GID, образов и доступных журналов.
Для внешней доставки нужен HTTPS. Пример доступа к UI — SSH-туннель
на localhost:18180; наличие конфигурации не означает, что collector включён.
UI не имеет multi-user login: не публикуйте его в Интернет.

## Проверки разработки

```sh
docker compose -f deploy/compose.test.yaml build
docker compose -f deploy/compose.test.yaml run --rm backend-test
docker compose -f deploy/compose.test.yaml run --rm frontend-test
python3 tests/compose_smoke.py
python3 tests/vector_smoke.py
```

Chromium: отдельный необязательный тестовый image (~2.4 GB), в runtime не нужен:

```sh
docker build -f deploy/browser.Dockerfile -t attackscope-browser-test .
docker run --rm --init --network host --shm-size 256m --cap-drop ALL --security-opt no-new-privileges:true -v "$PWD/tests:/tests:ro" attackscope-browser-test /tests/browser_smoke.py
```

Browser smoke предполагает запущенное приложение с investigation demo.
CI описан в `.github/workflows/ci.yml`. Его результаты проверяйте во вкладке Actions.
`docker compose down` останавливает приложение и сохраняет volume.
