# Классификация v0.1

Наблюдения остаются событиями, findings — отдельная сущность. Worker каждые 2 s
берёт до 100 pending events, группирует работу по правилу/host/IP/окну.
В одной SQLite write transaction пересчитывает группы, upsert finding и удаляет
pending. Crash до commit откатывает всё; restart продолжает очередь.
Поздняя доставка пересчитывает своё event-time окно. Delivery duplicates не
попадают в очередь и не увеличивают counters. IP null не классифицируется.

Правила версии 1, кроме sensitive_path v2; default env ATTACKSCOPE_*:

| Rule ID | Метрика | Порог | Окно |
|---|---|---|---|
| ssh_bruteforce | failure/invalid_user count | SSH_FAILURE_THRESHOLD=10 | SSH_WINDOW_SECONDS=300 |
| web_rate | HTTP requests count | WEB_REQUEST_THRESHOLD=120 | WEB_RATE_WINDOW_SECONDS=60 |
| web_paths | distinct HTTP paths | WEB_PATH_THRESHOLD=30 | WEB_PATHS_WINDOW_SECONDS=300 |
| sensitive_path (v2) | known sensitive path | 1 | 300 s |
| port_probing | distinct observed destination ports | PORT_THRESHOLD=10 | PORT_WINDOW_SECONDS=300 |

Чувствительные пути заданы в classification/engine.py. Сравнение case-insensitive,
query удалён ранее. Совпадение не доказывает компрометацию, нет SQLi/XSS success.
404 само по себе не является триггером. Firewall видит лишь логируемые пакеты.

В sensitive_path v2 добавлены наблюдавшиеся пути AWS config/credentials,
Azure credentials, Google Cloud application_default_credentials.json, Docker
config.json/.dockerenv, .config, Bazaar metadata, /admin/config.php и конкретные
варианты .env.local/.production/.development/.bak. Это точный список, не поиск
подстрок: /docs/.aws/credentials или /.env.example сами по себе не срабатывают.
Конфигурационные пути также могут использоваться для fingerprinting; срабатывание
означает наблюдаемое обращение к известному пути, а не доказанную кражу секрета.
Код ответа, включая 307 или 404, не доказывает успех или неуспех атаки в целом.

reason.matched_paths содержит до 20 разных наблюдавшихся путей;
matched_paths_truncated отмечает обрезку. event_count учитывает все совпавшие
события окна. Версия входит в ID finding и cache key. Старые v1 findings не
перезаписываются при обработке v2. Фонового массового пересчёта истории нет;
новое/позднее событие может пересчитать своё окно по текущему правилу.

Каждый finding хранит rule ID/name/version, config snapshot, threshold/observed,
window UTC [start,end), actual count и первые 100 evidence IDs. Флаг truncation
явный. IDs после detail retention могут вести на 404: это не новые события.
Raw event classification указывает последнее совпавшее правило; все findings
сохраняются отдельно. Severity при совпадении становится medium; это оценка
наблюдаемой активности, не критичность подтверждённого инцидента.

## Решение о временных окнах

Для MVP выбраны фиксированные UTC окна: floor(timestamp/window)*window.
Альтернатива rolling windows точнее на стыке, но требует больше пересчётов при
late delivery и контроля размера состояния. Fixed окна проще восстанавливать,
дедуплицировать и объяснять. Цена: последовательность на стыке может не достичь
порога ни в одном окне. Это documented limitation, а не полноценный IDS.
Порог/окно входят в deterministic finding ID; изменение настроек применяется
к последующей работе, старые findings не переименовываются и не пересчитываются
задним числом. Для пересчёта истории нужен отдельный будущий workflow.

GET /api/v1/findings: общие time/host/IP/source/category/severity/port filters,
не более 500 результатов, явный truncated. На плотном диапазоне сузьте время.
Timeline показывает их ромбами, наблюдения — кружками. При открытии доступны
основания, ссылки на события и переход к IP.

SSH threshold считает наблюдаемые failure/invalid_user записи, не уникальные
сессии: один login может дать несколько journald messages. Это ограничение
источника/простого правила, а не точный счётчик уникальных попыток входа.

## Операторские проверки

UI помечает известные User-Agent приёмочных HTTP-запросов как «Возможная проверка
оператора». Список префиксов находится в frontend/src/lib/operatorCheck.ts;
пометка доступна для уже сохранённых событий без backfill. Это подсказка по
недоверенному тексту: любой клиент может подделать User-Agent. Подсказка не
меняет severity, classification, evidence, API, export и counters, не скрывает
события и не исключает их из правил. Даже /.aws/credentials с таким User-Agent
обрабатывается как sensitive_path. SSH-входы по одному IP автоматически не
объявляются операторскими.
