# 08. Установка, сбор и эксплуатация

[Вики](README.md) · [Назад: расследования](07-investigations.md) · [Далее: диагностика](09-troubleshooting.md)

Раздел предназначен для оператора self-hosted установки. Сначала определите
контекст: обычный локальный Compose, рабочая VM с `.env` и Unix socket либо
временный docs-стенд. У них разные проекты, данные и способы доступа.

## Состав установки

| Компонент | Назначение | Данные |
|---|---|---|
| Backend | Validation, normalization, storage, classification, read API | SQLite WAL, source hashes, rollups/findings |
| Frontend / Nginx | React-приложение и разрешённые read API routes | Статические assets |
| Vector при подключении | Чтение журналов, проекция, доставка с auth и retries | Checkpoints и ограниченные очереди |

SQLite и фоновые workers находятся в одном приложении. Отдельные Redis,
Kafka, Elasticsearch или Kubernetes для v0.1 не требуются.
Пример для VM включает systemd backup/restore/health/rotation после настройки оператором.
Обычный локальный quickstart эти host timers не устанавливает.

## Первый запуск и конфигурация

Используйте [INSTALLATION.md](../INSTALLATION.md). Базовая последовательность:

```sh
docker compose config --quiet
docker compose up --build --wait
docker compose ps
```

Без `.env` используются defaults проекта. Если нужна настройка, создайте свой
файл по [.env.example](../../.env.example), не перезаписывая действующий.
Локальный UI по умолчанию доступен на localhost:8180.

Сроки хранения, размеры input/batch, rate/concurrency и thresholds задаются
environment. Изменение файла само по себе не меняет уже работающий процесс:
нужно контролируемое пересоздание соответствующего контейнера.
Перед уменьшением retention оцените последующее удаление старых данных.

## Подключение новой VM: порядок работ

1. Определите нужные источники и формат реально доступных журналов.
2. Зарегистрируйте host в backend.
3. Создайте отдельный source token для каждого kind на этом host.
4. Обеспечьте защищённую доставку: для внешней VM HTTPS с проверкой
   сертификата/hostname и обязательной source authentication.
5. Подготовьте Vector по существующим примерам, не меняя службы автоматически.
6. Проверьте transform локально и ограничьте объём доставки.
7. Передайте одно явно помеченное проверочное наблюдение.
8. Убедитесь, что оно появилось у правильного host/kind, затем проверьте retries.

Аутентифицированный source определяет host. Одного VPN без source auth недостаточно
для защиты от подмены одного агента другим. Токены не должны попадать в Git,
открытые `.env.example`, вывод команд, UI или публичные журналы.

Примеры CLI и envelope: [INGESTION.md](../INGESTION.md).
Форматы и Vector: [COLLECTION.md](../COLLECTION.md).
TLS-вариант: [OPERATIONS.md](../OPERATIONS.md).

### SSH / journald

Поддерживаются доступные записи success, failure, invalid_user и disconnect.
Vector читает journal read-only; доступ к journal может давать чтение большего
объёма, чем выбранные sshd events. Ограничение по unit в конфигурации не равно
отдельному filesystem ACL только для SSH.

В действующем pinned варианте используется current boot и checkpoint. При
volatile journal данные прошлой загрузки host могут отсутствовать. Первая
настройка может начинать сбор с момента подключения, без импорта старой истории.
Реальные детали — [PRODUCTION.md](../PRODUCTION.md).

### Nginx JSON

Выделенный JSON access log позволяет явно выбрать поля:

| Поле | Источник / смысл |
|---|---|
| timestamp | Время запроса, нормализованное к UTC |
| remote_addr | Наблюдаемый адрес клиента |
| request_method | HTTP method |
| path | `$uri`, без query values |
| status | HTTP status |
| user_agent | Недоверенный текст клиента |
| request_id | Стабильная ссылка для повторной доставки |
| dst_port | Известный порт Nginx |
| duration_seconds | `$request_time`, преобразуемый к duration_ms |

Готовый фрагмент — [nginx-logging.conf](../../deploy/production/nginx-logging.conf).
Authorization, Cookie и body в него не включаются. Изменение Nginx на реальном
сервере является отдельной операторской операцией с backup и `nginx -t`.

Не доверяйте X-Forwarded-For без явной архитектуры trusted proxy. В зависимости
от маршрута локальный запрос может иметь source IP Docker bridge gateway.
Это не обязательно внешний адрес клиента и не показатель личности.

### Firewall

Адаптер понимает доступные nftables/iptables journal records, но сам не включает
логирование и не меняет правила. Подготовьте отдельное ограниченное rate-limited
логирование и оцените охват. Нельзя включать неограниченный log всего трафика
только ради заполненной дорожки Timeline.

Наличие примера конфигурации не означает, что collector уже запущен на host.
Новая VM может законно иметь только SSH/HTTP и пустую Firewall-дорожку.

## Проверка здоровья

В контексте **своего** Compose-проекта:

```sh
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
```

Operational logs просматривайте приватно. Для обращения за помощью подготовьте
sanitized фрагмент, request ID и версии; не публикуйте токены или сырые журналы.

После установки и проверки примера обслуживания доступны:

```sh
sudo systemctl list-timers 'attackscope-*'
sudo systemctl start attackscope-maintenance@check.service
sudo systemctl show attackscope-maintenance@check.service -p Result -p ExecMainStatus
```

Проверка смотрит контейнеры, read API, свободный диск, свежесть backup и ошибки
коллектора. Один successful health-check не устанавливает полноту логирования
и отсутствие компрометации всех приложений VM.
Внешние уведомления по этим проверкам пока не настроены.

## Резервное копирование

При WAL недостаточно скопировать один `.db` во время работы. Штатная команда
использует SQLite backup API и проверяет integrity/FK:

```sh
docker compose exec backend python -m attackscope.backup --output /data/backups/manual-before-update.db
```

Для следующей копии выберите новое имя: существующие файлы не перезаписываются.
Готовый snapshot можно перенести операторским способом из контейнера.

Для полного восстановления важны не только события:

- согласованный snapshot SQLite;
- соответствующие source tokens / private credentials;
- image IDs и версия приложения;
- применённые конфигурации и сведения о каталогах/UID.

Hash токена в БД не позволяет восстановить его секрет. Экспорт CSV/JSON тоже
не заменяет DB backup. Полную копию храните приватно; внешнее хранение/шифрование
нужно организовать отдельно.

После настройки примера доступны задания:

```sh
sudo systemctl start attackscope-maintenance@backup.service
sudo systemctl start attackscope-maintenance@restore-check.service
```

Scheduled backups содержат `.db`, sidecar `.sources.json` и `.metadata.json`.
По политике примера сохраняется до семи snapshots с дисковым бюджетом;
новейшая успешная копия сохраняется даже при превышении бюджета одной копией.
Копия на той же VM не защищает от потери самой VM. Подробности и фактические
таймеры — [PRODUCTION.md](../PRODUCTION.md).

## Обновление и откат

Для заранее подготовленной VM frontend обновляется из локального чистого Git:

```sh
./scripts/deploy production --component frontend --host vm.example.com --user operator --identity ~/.ssh/id_ed25519
```

Команда проверяет код, собирает immutable image по SHA, передаёт его по SSH,
запускает закрытого кандидата и браузерные проверки, затем переключает frontend.
При ошибке пытается вернуть предыдущий образ. Во время переключения возможен
короткий перерыв UI. Для backend эта команда пока не предназначена.

Backend обновляется отдельной согласованной процедурой. Нужно проверить backup,
новый образ на копии БД, миграции/совместимость и доставку после перезапуска.
Старый image не гарантирует работу с новой схемой; возврат образа и восстановление
snapshot — разные операции. Сохранение новых событий при откате требует отдельного
решения. Процедура последней выкладки — [DEPLOYMENT.md](../DEPLOYMENT.md).

Не запускайте несколько backend-процессов на одном рабочем SQLite-файле.
Кандидат, пишущий в копию БД, и второй backend на том же рабочем volume —
разные схемы проверки.

## Retention и место

Cleanup работает небольшими пакетами в фоне. После большого простоя физическое
удаление может догонять постепенно, хотя read API уже исключает истёкшие details.
Размер SQLite-файла не обязан сразу уменьшаться: освобождённые страницы
используются повторно. Удаление `.db-wal` вручную не является очисткой диска.

Контролируйте также Vector disk buffers, access logs, архивы images и backups.
Они имеют собственные правила хранения. Массовый Docker prune или удаление
volume не является безопасной универсальной диагностикой AttackScope.

## Что не делать автоматически

Не применять команды из журналов, не выдавать runtime доступ к Docker socket,
не включать privileged ради чтения событий, не менять SSH/firewall вслепую
и не публиковать UI с отсутствующей многопользовательской аутентификацией.
Согласованные изменения реальной инфраструктуры выполняет оператор.

**Далее:** [09. Диагностика проблем](09-troubleshooting.md).
