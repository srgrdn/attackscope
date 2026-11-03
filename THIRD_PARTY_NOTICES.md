# Сторонние компоненты

Лицензия самого AttackScope пока не выбрана. Ниже metadata runtime dependencies из lockfile
и установленных пакетов; тексты frontend licenses входят в public/third-party-notices.txt
и распространяются вместе с UI. Python wheel license files остаются в image.

| Frontend package | Version | License |
|---|---|---|
| @radix-ui/react-compose-refs | 1.1.5 | MIT |
| @radix-ui/react-slot | 1.5.0 | MIT |
| @tanstack/query-core | 5.105.2 | MIT |
| @tanstack/react-query | 5.105.2 | MIT |
| @types/react | 19.3.0 | MIT |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| csstype | 3.2.3 | MIT |
| echarts | 6.1.0 | Apache-2.0 |
| lucide-react | 1.66.0 | ISC |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| scheduler | 0.28.0 | MIT |
| tailwind-merge | 3.7.0 | MIT |
| tslib | 2.3.0 | 0BSD |
| zrender | 6.1.0 | BSD-3-Clause |

Backend runtime использует MIT (FastAPI/Pydantic/SQLAlchemy/Alembic/Mako/AnyIO),
BSD-3-Clause (Starlette/Uvicorn/Click/MarkupSafe/python-dotenv/idna),
Apache-2.0 (opentelemetry-api), PSF-2.0 (typing_extensions),
MIT AND PSF-2.0 (greenlet). Точные версии — backend/requirements.lock.

Отдельные образы: Python/Alpine и Nginx сохраняют собственные OS/package licenses;
Vector — MPL-2.0, не включён в код AttackScope; ECharts — Apache-2.0.
shadcn/ui Button — MIT adaptation, см. исходный файл.
Контейнеры сохраняют upstream notices; полный OS SBOM/independent legal audit
не выполнялся. Перед внешней публикацией binary distribution следует повторить
license/security inventory для точных digest и сохранить notices.

Dev-only minimatch override 11.0.1 устраняет GHSA-g3hv-75wg-m249. Обновление major
проверено на API, используемом ESLint (Minimatch.match); удалённые makeRe/AST
в нашем lint workflow не используются. Полные lint/types/tests/audit проходят.
