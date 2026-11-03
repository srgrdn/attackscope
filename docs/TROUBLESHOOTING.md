# Troubleshooting

- **Access Error:404**: убедитесь, что открыт http://localhost:8180. Порт8080 на
  Windows этого стенда обслуживал другой web server. `docker compose ps` покажет binding.
- **Пустая Timeline**: выбрать 24h/7d, очистить фильтры, проверить UTC диапазон.
  Для нового demo использовать новое run-name. При старом имени его base time не
  меняется; повтор защищён dedup. Новые случаи — `--scenario investigation`.
- **Backend unavailable**: `docker compose ps`, `docker compose logs --tail=100 backend`.
  Проверьте volume permissions (UID10001), место, migration error и memory limit.
  Не удаляйте volume для исправления readiness.
- **Ошибка Docker build cache в sandbox Codex**: задайте отдельный разрешённый
  временный каталог `DOCKER_CONFIG=/tmp/attackscope-docker`. Это рабочий cache CLI,
  не изменение существующих Docker credentials и не отключение sandbox.
- **401/403 ingestion**: проверьте индивидуальный token, enabled source/host и kind.
  Не печатайте токен в logs и не подставляйте чужой host_id.
- **422**: RFC3339 с timezone, JSON array, разрешённые values/source, timestamp
  не старше retention и не более5m в будущем, полный batch отклоняется атомарно.
- **429/503**: backpressure/rate/query/writer limit; повтор с паузой. Demo повторяет
  временные ответы, Vector sink retries. Для read query сузьте диапазон/добавьте IP.
- **410/cursor expired**: detail недоступен или pagination старше15m. Обновите
  таблицу; для старой активности откройте «История до365d».
- **413 export**: сузьте фильтры до10000 events/8MiB. Частичный файл не выдаётся.
- **Findings нет**: дождитесь worker, проверьте thresholds/fixed UTC window.
  Одиночный404 не атака; соседние окна могут не достигать порога.
- **История меньше detail**: historical view считает только полные UTC часы,
  фактический effective range указан. URL/status/outcomes после30d не сохраняются.
- **Vector env не подставились**: версия0.61 требует явный
  --dangerously-allow-env-var-interpolation для приведённых env-based примеров.
- **Unknown journald format /422**: сверить сообщения с поддержанными fixtures;
  добавить parser test до расширения формата, отфильтровать неподдержанное на агенте.
- **GeoIP/ASN unavailable**: базы нет; приложение не подставляет фиктивные страны.

Перед обращением сохраните версии, sanitized error code/request ID и шаги
воспроизведения. Не прикладывайте реальные исходные журналы, credentials и .db.
