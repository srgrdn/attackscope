# Установка

Поддерживаемый запуск: Docker Engine + Compose v2 на Linux, либо Docker в WSL2.
Host Python 3.10 и Node 20 не нужны: backend собирается с Python3.12,
frontend с Node24. На небольшом VPS оценивайте собственные throughput/объём
журналов по PERFORMANCE.md. RAM limits runtime 512m/128m, build и тесты требуют
дополнительных ресурсов; это не обещание суммарной памяти VPS.

1. Клонировать https://github.com/srgrdn/attackscope.git и перейти в его каталог.
2. При необходимости создать `.env` по `.env.example`. Не копировать поверх
   существующего файла; source tokens в `.env.example` отсутствуют.
3. `docker compose config --quiet`
4. `docker compose up --build --wait`
5. `docker compose exec backend python -m attackscope.demo --run-name morning --scenario investigation`
6. Открыть http://localhost:8180. Входы фильтров и шкала используют UTC;
   формат отображения native-полей даты зависит от браузера и ОС.

Первый запуск скачивает pinned base images и зафиксированные зависимости,
создаёт volume attackscope-data и автоматически применяет Alembic migrations.
Не выполняет системные установки, mount Docker socket или изменение правил VM.
В Compose два non-root контейнера; ingress/read API разделены внутри backend.
Другие Compose-проекты не затрагиваются.

База — /data/attackscope.db в named volume; секреты демо — /data/demo, созданные
CLI токены — выбранный приватный путь /data/secrets. Не добавляйте их в Git.
HTTP ingestion наружу не опубликован. Подключение агентов — COLLECTION.md.
Для удалённого просмотра оператор может использовать SSH forward localhost8180;
не менять bind на 0.0.0.0 без отдельной UI authentication/TLS архитектуры.
Для отдельной VM предусмотрен [закрытый вариант с Unix-сокетом](VM_DEPLOYMENT.md):
он не публикует host ports и подходит также при известном ограничении
localhost-публикации Docker до28.0.0. Использовать его по отдельному согласованию
оператора, с заранее собранными образами и приватным каталогом сокета.

Windows: используйте localhost:8180. На этом стенде 8080 занят другим приложением,
которое отвечало Access Error:404; внутренний порт Nginx остаётся 8080, это нормально.
В `docker compose ps` опубликован именно 127.0.0.1:8180 →8080.

Остановка: `docker compose down` (без удаления volumes). Удаление volume с
пользовательскими данными не является частью установки/обновления.
