# Хранение и historical coverage

По умолчанию detail 30d, hourly event_rollups и findings 365d, delivery keys 30d.
TTL вычисляется по UTC часам. Один backend worker раз в минуту удаляет до 1000
строк каждой таблицы в транзакции, с query deadline и retry на следующем цикле.
Очистка eventual: после большого простоя физическое удаление догоняет постепенно;
read API немедленно исключает истёкший detail по cutoff.

При удалении detail pending удаляется CASCADE, delivery_keys.event_id → null,
rollup counters не уменьшаются. Повторная доставка с ещё живым ключом не создаёт
событие, даже если его detail уже удалён. После dedup TTL гарантии replay нет.
SQLite освобождённые страницы использует повторно: файл не обязан уменьшаться.
Автоматического VACUUM и разрушения БД нет. WAL auto-checkpoint стандартный;
долгие readers ограничены SQL deadline. Backup должен использовать SQLite API,
не копирование одного .db при активном WAL.

GET `/api/v1/history`: from/to до aggregate retention, host/IP/source/category/
destination port filters. Только полные UTC часы (ceil(from), floor(to)); точные
counts и effective_from/to возвращаются явно. Частичные часы не оцениваются
пропорционально. На коротком диапазоне без полного часа результат пустой.
До 31d график по часам, дальше по дням. Распределения top 100 + truncated.
Полей path/status/SSH outcomes/severity/raw detail в rollups нет: они недоступны
после detail TTL. Severity filter historical API отклоняет, не игнорирует.
В UI отдельная «История до 365d» с 90d/365d и произвольным диапазоном.

Findings хранятся до aggregate TTL; evidence IDs могут истечь раньше. Их подробные
ссылки не обещают доступность события. IP first/last основаны на retained rollups.
Если изменить thresholds, старые findings сохраняют собственный snapshot.

Проверки: retention повторно без double decrement, старый event удалён/rollup жив,
delivery key сохраняется с null event_id, aggregate TTL, точность границ полного
часа. Индексы и миграции включены в общий suite.

Worker window cache обновляется только после commit, хранит received-at watermark
до 4096 окон; late event с новым received_at вызывает пересчёт. Это оптимизация,
не источник истины. Queue и findings транзакционно остаются в SQLite.
