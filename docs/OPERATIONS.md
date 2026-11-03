# Обновление, резервное копирование и восстановление

## Backup

SQLite при WAL нельзя надёжно сохранить простым копированием одного .db.
Команда ниже использует SQLite backup API, создаёт новый файл mode0600,
проверяет integrity/FK и никогда не заменяет существующий файл:

```sh
docker compose exec backend python -m attackscope.backup --output /data/backups/manual-before-update.db
```

Выберите новое имя для следующего backup. Скопируйте готовый файл из контейнера
в защищённое внешнее хранилище операторским способом (`docker compose cp`).
Не публикуйте его: он содержит IP/history и hashes источников. Приватные token
files /data/secrets и /data/demo хранятся отдельно; для полной операторской
резервной копии защитите и их. Потерянный source token можно заменить новым
через create-source и disable-source; старый секрет не восстанавливается из hash.
Приложение не шифрует SQLite самостоятельно: шифрование тома/backup — задача host.

## Обновление

1. Проверить release notes, свободное место и текущую схему. Создать новый backup.
2. Получить проверенную версию кода из GitHub и изучить изменения.
3. `docker compose build`
4. `docker compose up -d --wait`
5. Проверить readiness, Timeline, API и реальные agent logs.

Миграции автоматически применяет единственный backend при старте. Не запускайте
несколько экземпляров backend на одной SQLite DB. Если запуск не удался,
сначала исследуйте логи; не выполняйте downgrade поверх пользовательских данных.
Старый image не гарантирует совместимость с новой схемой. Retention settings
применяются после restart; уменьшение TTL приводит к последующей очистке.

## Восстановление

Автоматической команды перезаписи рабочей базы намеренно нет.
Порядок для оператора: остановить ingestion и backend, сохранить текущий volume
как отдельную копию, проверить backup в **новом** пустом volume/каталоге и запустить
его с соответствующей версией приложения. Лишь после проверки вручную переключить
Compose на восстановленный volume. Существующие .db/-wal/-shm не смешивать
с файлами другой копии. Токены агентов должны соответствовать hashes в backup;
при откате новые после backup источники потребуется создать заново.

Безопасная локальная проверка восстановления: tests/test_backup.py создаёт
изолированную БД, делает snapshot, открывает его как новый engine, применяет
миграции и проверяет host/integrity, исходная БД остаётся неизменной.
Пример backup и проверки восстановления на отдельной копии:
[PRODUCTION.md](PRODUCTION.md). Настройку своей установки проверяет оператор;
проверка копии не равнозначна испытанию аварийного восстановления всего сервера.

## Опциональный TLS ingestion

`deploy/compose.ingress.yaml` добавляет только HTTPS ingestion proxy к backend8001.
По умолчанию также localhost8443; UI/read API наружу не добавляются. Укажите
ATTACKSCOPE_TLS_CERT_FILE/KEY_FILE (абсолютные пути) и TLS UID/GID, способный читать
ключ без ослабления его доступа. Для подключения VM оператор явно задаёт
ATTACKSCOPE_INGEST_BIND своим private/public IP и обеспечивает firewall/DNS/сертификат.
Self-signed локальный тест не заменяет валидный certificate chain на реальном сервере.

```sh
docker compose -f compose.yaml -f deploy/compose.ingress.yaml config --quiet
docker compose -f compose.yaml -f deploy/compose.ingress.yaml up -d --wait
```

Не отключать TLS verification на агенте. Токен по-прежнему обязателен даже в VPN.
Rate limit proxy может объединять VM за NAT по IP; при sizing учтите burst/retries.
Конфиг не загружает сертификаты, не меняет credentials/firewall и не устанавливает
сертификаты в системное trust store. Это опциональный операторский запуск.
