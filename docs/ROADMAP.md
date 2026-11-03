# Roadmap и состояние публичного исходного кода

## MVP v0.1

Реализованы backend/frontend skeleton, authenticated batch ingestion,
versioned normalization, SQLite WAL/migrations, deduplication, bounded queries,
Timeline с server aggregation и деталями, Vector adapters SSH/HTTP/firewall,
explainable classification, IP Explorer, Overview, Event Explorer/export,
retention/hourly history, backup, документация и CI configuration.

Пользовательский вход: [USER_GUIDE.md](USER_GUIDE.md), [вики](wiki/README.md).
Доступны 12 настоящих UI screenshots на синтетическом наборе из 2093 событий.
Скриншоты не содержат рабочих журналов и credentials. Error API state явно
смоделирован в браузере. Происхождение — docs/images/manifest.json.

Локальный запуск — http://localhost:8180; demo investigation — 2086 событий.
Наличие конфигураций VM/Vector не означает, что реальные источники подключены.
Код не выполняет автоматическую настройку реальных серверов.

## Подготовка первой публикации

Публичная история начинается одним новым root commit. Прежние локальные
коммиты и private operational reports в неё не включены. Убраны реквизиты
конкретного сервера и разовые host maintenance scripts. Общие примеры используют
адреса документации, vm.example.com и /srv/attackscope. Deployment требует
явных --host/--user; SSH private keys и passphrase в репозитории отсутствуют.
Лицензия самого проекта пока не выбрана; сторонние license notices сохранены.

Результаты проверок перед публикацией записываются в [PUBLICATION.md](PUBLICATION.md).
Отдельный журнал эксплуатации конкретных VM не является частью публичной вики.

## Ограничения и следующие версии

GeoIP/ASN возвращает unavailable без установленного provider; нет автоблокировок,
LLM, multi-user login и системного мониторинга. UI не предназначен для Интернета.
Нагрузочные измерения ограничены описанными сценариями: [PERFORMANCE.md](PERFORMANCE.md).
Интеграции CrowdSec/WAF/Suricata, reputation и карты — будущие отдельные задачи.
