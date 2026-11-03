# Overview, Event Explorer и экспорт

Overview различает total_events, http_requests, suspicious_events,
suspicious_http_requests и suspicious_sources. Подозрительными считаются события,
отмеченные правилами; worker обрабатывает очередь асинхронно. Неизвестный IP
не добавляется к уникальным адресам. Группировки top 100 с явным truncated.
Временной график отвечает на вопрос, когда наблюдались события; CPU/RAM нет.

Event Explorer: диапазон UTC, IP, host, source, category, destination port,
severity, сортировка timestamp asc/desc, keyset pages по 100. Курсор 15 min,
новые received events не добавляются посреди цепочки страниц. Обновление начинает
новый snapshot. Открывается sanitized card; raw original никогда не возвращается.

GET `/api/v1/overview`: обязательные from/to и общие фильтры.
GET `/api/v1/events/export.csv` и `.json`: те же фильтры и сортировка; limit
страницы игнорируется, cursor запрещён. Выгружается весь выбранный набор
до 10000 событий /8 MiB. При превышении — 413 до отправки любого файла.
CSV: quote-all, dangerous leading `= + - @` (после whitespace), tab/CR/LF
экранируются ведущим апострофом. JSON не содержит исполняемой разметки.
Headers attachment/no-store/nosniff. Экспорт не включает source tokens.

Demo investigation: `docker compose exec backend python -m attackscope.demo
--run-name morning --scenario investigation` (одной строкой). 2086 безопасных
синтетических событий: benign 404, SSH success/disconnect, SSH failures,
web scanning, sensitive paths, IPv6 observed ports. Повтор с тем же именем
идемпотентен. Адреса только documentation ranges; запросы наружу не выполняются.

Проверки: filtered CSV/JSON roundtrip, redaction, formula injection unit cases,
Overview total vs suspicious; frontend lint/types/tests/build. Доступ через Nginx
допускает только перечисленные read paths. Пример закрытого развёртывания описан
в [PRODUCTION.md](PRODUCTION.md); доступ к UI организуется через SSH-туннель.
