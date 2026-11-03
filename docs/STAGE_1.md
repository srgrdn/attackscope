# Этап 1 — Project Skeleton

Статус: выполнен, перед Этапом 2 требуется согласование следующего плана.

## Что создано

- FastAPI read app и изолированное ingestion app (пока только health).
- Общий lifecycle двух Uvicorn listeners: pre-bind, SIGTERM/SIGINT, bounded shutdown.
- Pydantic Settings, SQLAlchemy connection pool, SQLite WAL/FK/FULL synchronous,
  проверка версии SQLite с исправлением WAL.
- Alembic baseline `0001_baseline`; automatic startup migration только для локального
  каркаса. Domain tables и приём событий относятся к Этапу 2.
- React/TypeScript strict shell с dark responsive layout, источниками SSH/HTTP/Firewall,
  честным placeholder Timeline и реальным backend readiness через TanStack Query.
- shadcn/ui Button pattern, Tailwind Vite plugin; MIT notice включён в static assets.
- Dockerfiles с test/runtime stages, root Compose и отдельный test Compose project,
  named data volume, localhost UI port, non-root runtime и read-only rootfs.
- README, .env.example, ignore files, Python hashed locks и npm lockfile.
- CI workflow с pinned checkout SHA; workflow пока не запускался на GitHub.

## Проверенные версии

| Компонент | Версия |
|---|---|
| Docker Engine | 27.2.0 |
| Docker Compose | v2.36.0-desktop.1 |
| Python (container) | 3.12.16 |
| SQLite (Python runtime) | 3.53.4 |
| FastAPI | 0.162.0 |
| Pydantic / Settings | 2.14.2 / 2.16.2 |
| SQLAlchemy / Alembic | 2.0.55 / 1.20.1 |
| Uvicorn | 0.54.0 |
| React | 19.3.1 |
| Vite / TypeScript | 8.3.5 / 5.9.3 |
| Tailwind / TanStack Query | 4.3.3 / 5.105.2 |
| Vitest / ESLint | 5.1.0 / 10.14.0 |
| pytest / Ruff / mypy | 9.2.0 / 0.17.3 / 1.20.2 |
| Python lock generator | pip-tools 7.6.2 |

Python, Node и Nginx образы pinned по digest в Dockerfiles. Зависимости проверялись
по официальным реестрам; lockfiles содержат конкретные версии и integrity/hashes.
SQLAlchemy намеренно ограничен веткой 2.0, TypeScript — совместимой 5.9; обновление
major/minor compiler отдельно проверяется. Версия host Python 3.10 не используется
для запуска приложения.

## Проверки и результаты

- `docker compose config --quiet` и test Compose config: успешно.
- Production Docker images backend/frontend: собраны.
- `docker compose up -d --wait --wait-timeout 60`: оба сервиса healthy.
- `GET /`: UI HTML, production JS/CSS доступны; readiness proxy возвращает ready.
- Frontend liveness: 200; ingestion через UI: 404; неизвестный Host: 421.
- Docker inspect: runtime user 10001:10001, rootfs read-only, cap_drop ALL;
  backend ports не published, UI binding 127.0.0.1:8080.
- Backend restart: готовность восстановилась, inode SQLite файла и baseline сохранены.
- Ruff check/format и mypy strict: успешно, 10 backend source files без type errors.
- pytest: 23 passed. Проверены config bounds, per-connection pragmas/FK,
  transaction rollback, empty/idempotent migrations/reopen/roundtrip,
  readiness при schema drift/unmigrated DB, route isolation,
  unsafe SQLite rejection, реальные listeners/SIGTERM и occupied-port startup failure.
- Frontend ESLint/Prettier/tsc: успешно. Vitest: 6 passed (loading, readiness,
  error/retry, invalid payload, HTTP errors, abort signal). Production build успешен.
- Те же backend/frontend checks запущены в соответствующих test Docker images.

Первый запуск backend-test build был выполнен до окончания dev-lock generation и
не собрался; после генерации сборка прошла. Первые Ruff checks обнаружили две длинные
строки; форматирование исправлено. У Alembic добавлен path_separator=os для устранения
deprecation warning. Starlette TestClient выдаёт одно upstream предупреждение о
будущем отказе от HTTPX 0.28 compatibility в пользу HTTPX2; текущие тесты проходят.
Предупреждение не скрыто фильтром. Следующее изменение API tests должно включать
проверенный переход на новый transport.

## Как проверить самостоятельно

Из корня проекта:

```bash
docker compose up --build --wait
curl --fail http://localhost:8180/api/v1/health/ready
docker compose -f deploy/compose.test.yaml build --parallel
docker compose -f deploy/compose.test.yaml run --rm backend-test
docker compose -f deploy/compose.test.yaml run --rm frontend-test
```

Открыть http://localhost:8180. Ожидаются «Backend подключён» и подпись «Макет временной
шкалы». Остановить можно `docker compose down`, volume сохраняется.

## Ограничения и оставшиеся риски

Нет ingestion/events/auth источников, фильтров, интерактивной Timeline, Vector и
classification. Отключённые пункты навигации обозначены как будущие функции.
Тесты интерфейса выполнялись в jsdom; реальный браузер и визуальные viewport checks
не запускались. Нагрузочных измерений нет. Нет реальной VM и внешнего TLS listener.
UI без remote authentication доступен только локально; наружу публиковать нельзя.
Первый build требует сетевого доступа. Audit транзитивных лицензий/уязвимостей и
выбор лицензии проекта предстоят до релиза. CI пока проверен только локальными
эквивалентами команд, push и GitHub execution не выполнялись.

Следующий этап: events schema/migration, authenticated ingestion и host binding,
validation/sanitization, stable-ID dedup, batch transactions, filtered read API,
cursor pagination и integration/security tests. Начинать после согласования.

## Официальные источники реализации

- [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [SQLAlchemy SQLite transaction handling](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [Alembic shared connection](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)
- [SQLite WAL и исправленные версии](https://www.sqlite.org/wal.html)
- [Vite runtime requirements](https://vite.dev/guide/)
- [Tailwind Vite plugin](https://tailwindcss.com/docs/installation/using-vite)
- [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/quick-start)
- [shadcn/ui manual setup](https://ui.shadcn.com/docs/installation/manual)
- [Uvicorn 0.54.0 lifecycle source](https://github.com/Kludex/uvicorn/blob/0.54.0/uvicorn/server.py)

## Исправление после проверки пользователем

Первичные HTTP-проверки выполнялись из WSL и не выявили конфликт Windows localhost:8080:
Windows curl воспроизвёл точный ответ `Mbedthis-Appweb/12.0.0` с ошибкой 404.
Исправление меняет только внешний default port на 8180; внутри контейнера Nginx
по-прежнему слушает 8080. Исходный результат проверки binding выше относится к
первому запуску. Актуальные команды самостоятельной проверки обновлены.

Проверено после исправления: `/` возвращает 200 из WSL и Windows; Windows
`http://localhost:8180/api/v1/health/ready` возвращает 200 с ready. Проверены
production JS/CSS через Windows curl, Compose config и git diff --check.
Новых unit tests не добавлялось: изменены только внешний port и документация.
