# Сбор событий Linux / Vector

На согласованной VM теперь проверен настоящий SSH/journald и Nginx collector:
[production-настройка и результаты](PRODUCTION.md). Ниже — исходные независимые
примеры, а не автоматически применяемая конфигурация production.

Vector 0.61.0: три независимых примера deploy/vector/{ssh,nginx,firewall}.yaml.
Один source token на VM и тип источника. Backend назначает host по токену;
переданный hostname — лишь атрибут Nginx, не идентификатор доступа.
Установка и изменение настоящего сервера выполняются оператором отдельно.
Автоматический запуск root/privileged агента и mount Docker socket не нужны.
Для journald достаточно выделенного пользователя с доступом на чтение journal;
file source должен читать только отдельный JSON access log Nginx.

## Подключение

1. Создать host и три source через CLI (см. INGESTION.md), передать каждый секрет
   соответствующему процессу Vector без записи в репозиторий и shell history.
2. Подготовить HTTPS reverse proxy к внутреннему backend:8001. Публичный путь
   должен разрешать только POST /api/v1/ingest/events, body ≤1 MiB, TLS1.2+,
   access logs без Authorization. Проверять сертификат/hostname на агенте.
   Не публиковать backend:8000 (административный read API).
   Для теста допустим localhost SSH port-forward к ingestion плюс source auth;
   внешний ingestion port по умолчанию не опубликован.
3. Установить ATTACKSCOPE_INGEST_URL (полный HTTPS URL) и индивидуальный
   ATTACKSCOPE_SOURCE_TOKEN через защищённое окружение сервиса Vector.
4. Проверить конфиг `vector validate --dangerously-allow-env-var-interpolation --no-environment /path/config.yaml`,
   выполнить `nginx -t` вручную при подключении Nginx JSON примера.
5. Запустить Vector; проверить появление host/source событий в Timeline.
   Не отключать TLS verification. 401/403 — credentials/kind; 422 — формат/возраст.

Nginx пример deploy/nginx-access.example.conf сохраняет $uri без query,
не включает Authorization/Cookie/body. Forwarded-For не доверяется автоматически:
настройка доверенных upstream proxy — отдельная задача оператора.
request_id должен генерироваться Nginx ($request_id), а не браться из клиентского
заголовка: это ключ dedup. Без стабильного ID повтор будет отдельным наблюдением.

SSH/firewall journal → source_reference=SHA256(__CURSOR), если курсор доступен.
Если Vector не выдаёт курсор, ID null: гарантии dedup нет. Message ограничено
8192 bytes, на backend извлекаются только известные поля и оригинал отбрасывается.
Поддерживаются Accepted/Failed password/publickey/keyboard-interactive,
Invalid user и типовые disconnect; неизвестные форматы не выдаются за детекции.
Парсер firewall читает SRC/DST/SPT/DPT/PROTO/IN; неизвестные значения отклоняются.
LOG сам по себе не означает DROP. AS_DROP/AS_ACCEPT/AS_REJECT допустимы только
если оператор разместил log рядом с соответствующим verdict; AS_OBSERVE — null.

Пример ограниченного log без изменения verdict: deploy/firewall-logging.example.nft.
Он никогда не применяется приложением. Rate limiting теряет часть наблюдений;
AttackScope не отображает полноту сетевого трафика и не вычисляет истинный объём атак.

## Доставка и ограничения

HTTP sink JSON array, ≤100 events /262144 bytes, один concurrent request,
≤3 requests/s. Memory queue 1000 events с backpressure; при аварии Vector память
теряется. Это осознанный MVP компромисс: сырые journald сообщения не пишутся
в отдельный disk buffer. Успешный ответ только после commit backend.
Повторяемые 429/503/сеть обрабатываются sink retry; 4xx формат/credentials требуют
вмешательства оператора, не считаются доставкой. Один malformed event отклоняет
весь batch; проверяйте фактический формат SSH вашей системы перед подключением.
Неподдерживаемые сообщения следует фильтровать на агенте; журналы Vector не
направляйте обратно в тот же pipeline. Ограничьте хранение operational errors.

Исторически эти примеры проверялись локально. Позже SSH/Nginx отдельно проверены
на реальной VM, см. PRODUCTION.md. Внешняя TLS-доставка и настоящий firewall
источник остаются отдельными непроверенными сценариями.

Официальные контракты: https://vector.dev/docs/reference/configuration/sinks/http/,
https://vector.dev/docs/reference/configuration/sources/journald/,
https://vector.dev/docs/reference/configuration/sources/file/,
https://nginx.org/en/docs/http/ngx_http_log_module.html.

Vector 0.61 отключает env interpolation по умолчанию: для запуска этих примеров
добавьте `--dangerously-allow-env-var-interpolation` (или соответствующую переменную
VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true). Это явное разрешение читать
две предназначенные агенту переменные, а не разрешение отключать TLS. Не используйте
print-config: после interpolation конфигурация содержит source token.

Локально выполнены: 51 parser/ingestion tests, Ruff и mypy, validate всех трёх
конфигураций бинарником Vector 0.61.0-debian (digest
sha256:f6c23b5a7e16fb2838d33619ef7acf4bad2289a7cf22bc90efc2371f520c4ea2).
Реальный journald проверен в production-конфигурации; внешний TLS rollout не выполнялся.

Готовый необязательный TLS proxy: deploy/compose.ingress.yaml и ingress-tls.conf.
Порядок операторского включения описан в OPERATIONS.md. Он не запускается default
Compose и не открывает read API. Локальная проверка с временным сертификатом
использует проверку доверия и hostname, без изменения системного trust store.
