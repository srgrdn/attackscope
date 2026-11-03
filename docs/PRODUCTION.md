# Пример production-компоновки

Это обезличенная схема установки, а не сведения о работающем сервере.
Набор deploy/production предназначен для изучения и адаптации оператором.
Локальный quickstart его не устанавливает. Перед запуском проверьте все пути,
UID/GID, image tags, journal group, log mounts и ограничения вашей ОС.

## Контейнеры и доступ

- Один backend: SQLite WAL, миграции, ingestion/read API и фоновые workers.
- Frontend: статический React UI и разрешённые read API routes.
- Vector: отдельные SSH/HTTP sources, authentication и ограниченные disk buffers.
- UI: Unix socket в приватном каталоге и SSH-туннель, без публичных host ports.

В примерах deployment root `/srv/attackscope/production`, Compose project
`attackscope-production`. Эти значения нужно согласовать во всех файлах.
Backend/collector non-root, read-only root filesystem, cap-drop ALL,
no-new-privileges, memory/CPU/PID limits. Docker socket не монтируется.
Host helpers требуют доверенного доступа к Docker и не являются runtime-сервисами.

Один host может использовать внутренний HTTP между контейнерами с отдельными
source credentials. Для внешней VM нужен HTTPS с проверкой сертификата/hostname.
Один VPN не заменяет привязку source к host/kind на backend.

## Сбор и приватные данные

Vector читает journal read-only и выделенный Nginx JSON log. Доступ к journal
может раскрывать больше данных, чем выбранный unit. Проверьте current_boot_only,
since_now, checkpoints и доступность journal на вашей ОС.
До буфера оставляются разрешённые поля; raw SSH message не сохраняется.
Nginx fragment использует `$uri`, server-generated request_id и не включает
Authorization, Cookie, query values или body. X-Forwarded-For не доверяется
автоматически. Log format подключает оператор после backup и `nginx -t`.

Credentials хранятся в приватном файле secrets/sources.json с ограниченными
правами и доступом только нужному collector UID. Не добавляйте этот файл в Git.
Bootstrap создаёт новые sources только для новой базы; это не update command.
Примеры bootstrap/activate/package не изменяют Nginx другого приложения.
Оператор отдельно подготавливает dedicated log и его rotation/reopen.
Не запускайте вспомогательные root scripts на неподготовленной VM.

Disk buffers и retries не гарантируют отсутствие потерь при переполнении очередей,
удалении непрочитанных журналов или потере host. Укажите собственные лимиты.
Firewall adapter не меняет правила; пустая дорожка не доказывает отсутствие трафика.

## Backup и обслуживание

Пример содержит helper ops.py, template service и backup/restore-check/check/
logrotate timers. Они устанавливаются только после проверки оператором.
В logrotate.conf замените пример имени Nginx container до включения rotation.
Service ReadWritePaths, рабочие каталоги и права должны совпадать с установкой.

Backup сохраняет SQLite, соответствующие credentials и image metadata.
Каталоги и файлы держите приватными; offsite copy и encryption организуются
отдельно. Restore-check открывает snapshot в отдельной временной БД, не заменяя
рабочую базу. Проверка копии не заменяет аварийное восстановление всей VM.
Retention по умолчанию: detail 30d, rollups до 365d; backup policy отдельно.

После осознанной установки примера доступны команды:

```sh
sudo systemctl list-timers 'attackscope-*'
sudo systemctl start attackscope-maintenance@check.service
sudo systemctl show attackscope-maintenance@check.service -p Result -p ExecMainStatus
```

Не запускайте эти команды в чужой конфигурации, предполагая её совместимость.
Health-check не доказывает полноту доставки или отсутствие взлома.

Обновления frontend: [DEPLOYMENT.md](DEPLOYMENT.md).
Backup/restore: [OPERATIONS.md](OPERATIONS.md).
Подключение источников: [COLLECTION.md](COLLECTION.md), [INGESTION.md](INGESTION.md).
