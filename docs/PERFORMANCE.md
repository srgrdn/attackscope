# Нагрузка и границы v0.1

Локальный воспроизводимый benchmark, Python 3.12.16 / SQLite 3.53.4,
Linux 6.18.54.1 WSL2 x86_64, 12 видимых CPU, 7.46 GiB RAM VM.
Это измерение разработки с параллельными проверками, не спецификация VPS/SLA.

| Events | Ingest (s) | Events/s | Events p95 (ms) | Timeline p95 (ms) | Overview p95 (ms) | Peak process RSS (MiB) | DB (MiB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10000 | 14.838 | 674 | 14.55 | 93.59 | 185.17 | 77.85 | 16.39 |
| 100000 | 129.815 | 770 | 17.70 | 359.30 | 1740.73 | 79.17 | 162.80 |

Метод: normalize+persist batches 500, WAL/synchronous FULL, все indexes,
200 documentation IP, 40 paths, timestamps за 24h. Получение событий — 100 rows;
Timeline — bounded buckets; Overview — uncached полные группировки. По 10 запусков,
p95 = nearest rank (10-й). Через прямой Store, без HTTP/TLS/Vector overhead.
Classification отдельно: один cold batch 100 событий — 0.833/0.471 s; полный
backlog в этом benchmark не измерялся. В рабочем demo очередь 2086 событий
обработалась до нуля; есть bounded in-memory window cache (4096 keys), который
ускоряет уже проверенные окна. После restart он пуст; durable pending остаётся.
WAL в конце 7.23/10.78 MiB; закрытие соединений checkpoint-ит WAL.
EXPLAIN IP/time: covering index ix_events_src_ip_time_id, SEARCH, не SCAN.
Дополнительно индексированы host/IP/source/time для правил и delivery event_id
для FK SET NULL при retention: без последнего deletion мог бы сканировать keys.

Рабочие контейнеры после demo (до финальной сборки): backend ~95 MiB, Nginx ~9 MiB
(docker stats, включает page cache). Compose limits: backend 512m, frontend 128m,
pids 128. Это ограничения контейнеров, не обещание достаточности для любой нагрузки.
Параметры memory limits меняются через .env; не включают Docker daemon, build,
Vector и тестовый Chromium image. Browser test image ~2.4 GB нужен только checks.

Повторить в изолированном test container (working DB не монтируется):

```sh
docker compose -f deploy/compose.test.yaml build backend-test
docker compose -f deploy/compose.test.yaml run --rm backend-test python benchmarks/run.py --events 100000
```

Benchmark каталог должен быть включён в test image. Большие файлы живут только
во временном каталоге и удаляются после процесса. Для 1M выбранный script поддерживает
`--events 1000000`, но такой прогон не выполнялся. При существенно большей истории
uncached Overview может достичь 5 s SQL deadline и вернуть 503; сузьте диапазон,
используйте host/IP filter или historical rollups. Не заявляем проверенную ёмкость
1M и не увеличиваем deadline ради скрытия тяжёлого запроса.

Overview cache TTL 10 s /32 queries; timeline/events не кешируются. Все API queries
имеют SQL deadline; global/source/writer/body concurrency bounded. Classification
и retention тоже имеют deadline и rollback; 429/503 должен повторять агент.
Рост persistent pending при потоке выше evaluator throughput виден оператору
по DB; full throughput classification и тяжёлая конкурентная нагрузка требуют
отдельного sizing перед реальным массовым подключением VM.
