# 11. Обновление скриншотов и учебный стенд

[Вики](README.md) · [Назад: справочник](10-reference.md) · [Руководство](../USER_GUIDE.md)

Изображения — настоящие снимки React UI в Chromium. Они снимаются с отдельного
локального backend, а не с рабочей VM. Скрипты не читают production .env,
source tokens или настоящие журналы.

## Состав набора

| Файл | Что показано |
|---|---|
| [01-timeline-overview.png](../images/01-timeline-overview.png) | Общая карта и группы |
| [02-timeline-filtered.png](../images/02-timeline-filtered.png) | Шесть отдельных cloud probes одного IP |
| [03-event-explorer.png](../images/03-event-explorer.png) | Таблица с IP/source фильтрами |
| [04-event-detail.png](../images/04-event-detail.png) | Атрибуты и безопасная проекция |
| [05-finding-detail.png](../images/05-finding-detail.png) | Sensitive path v2, matched paths и evidence |
| [06-ip-explorer.png](../images/06-ip-explorer.png) | Распределения и история IP |
| [07-overview.png](../images/07-overview.png) | Верхняя сводка и динамика |
| [08-history.png](../images/08-history.png) | Фактический период полных часов |
| [09-operator-check.png](../images/09-operator-check.png) | Неподтверждённая операторская пометка |
| [10-empty-state.png](../images/10-empty-state.png) | Пустой отфильтрованный диапазон |
| [11-api-error.png](../images/11-api-error.png) | Error UI с смоделированным HTTP503 |
| [12-mobile-timeline.png](../images/12-mobile-timeline.png) | Узкое окно браузера |

Некоторые снимки захватывают всю страницу, другие — экран или отдельную карточку.
Overview на изображении показан с верхней части; нижние таблицы доступны
прокруткой в приложении. Изображения можно открыть отдельно для чтения мелких полей.

## Требования

- Linux / WSL с host Python 3.9+.
- Docker Engine и Compose не ниже 2.24.4 для `!override` overlay.
- Свободный локальный порт 18182.
- Достаточно ресурсов для сборки и отдельного Chromium image; он заметно больше
  runtime-приложения и не устанавливается на VM ради документации.
- Доступ к официальным образам/зависимостям при первом запуске или готовый cache.

Основной runtime не требует host Python. Здесь он нужен только для оркестратора
съёмки, использующего стандартную библиотеку. Playwright и браузер находятся в
существующем отдельном Dockerfile; дополнительных Python-пакетов на host не нужно.

## Полная регенерация

Из корня репозитория:

```sh
python3 scripts/docs_screenshots.py
python3 scripts/check_docs.py
```

Ожидаемый результат — 12 PNG и обновлённый `docs/images/manifest.json`.
После успешной съёмки временный проект останавливается и удаляется. После ошибки
он также очищается; прежние готовые изображения не заменяются частичным набором.
Локальные приложения на 8180 и SSH-туннель 18180 скриптом не меняются.

### Что делает оркестратор

1. Игнорирует inherited COMPOSE_* и ATTACKSCOPE_* overrides в своём процессе.
2. Проверяет, что фиксированный проект `attackscope-docs` ещё не существует
   и порт 18182 свободен.
3. Использует отдельный env example и Compose overlay.
4. Создаёт backend с `/data` в tmpfs, без рабочего named volume и без journal mounts.
5. Загружает investigation demo и семь документационных HTTP events.
6. Ждёт завершения классификации, чтобы screenshots не показывали случайные
   промежуточные counters.
7. Запускает Chromium, которому разрешены запросы только на docs origin.
8. Проверяет экраны перед съёмкой: нужный host, counts, finding v2, badge и empty/error.
9. Публикует готовый набор изображений и manifest.

Это обычная отдельная Docker bridge-сеть с frontend, опубликованным только на
127.0.0.1:18182. Изоляция данных обеспечивается собственным проектом/tmpfs;
браузер дополнительно блокирует запросы к другим origin. Это не отдельный
гарантированно air-gapped host.

## Оставить учебный стенд для ручного просмотра

```sh
python3 scripts/docs_screenshots.py --keep-running
```

После успешной съёмки откройте `http://localhost:18182`. Используйте адреса
из [сценариев](07-investigations.md). База временная: данные tmpfs теряются
после остановки контейнера. Этот режим не предназначен для реальных источников.

Остановить только этот стенд:

```sh
docker compose --env-file deploy/docs.env.example -p attackscope-docs -f compose.yaml -f deploy/compose.docs.yaml down
```

Перед повторной генерацией сначала завершите прежний docs-проект этой командой.
Скрипт не перезаписывает произвольный уже работающий Compose-проект под тем же именем.

## Учебные данные

Базовый [investigation.json](../../fixtures/investigation.json) содержит 2086 событий.
[documentation.json](../../fixtures/documentation.json) добавляет шесть cloud/config
probes с `198.51.100.42` и один операторский GET с `192.0.2.44`.
Итого при свежем запуске — **2093** наблюдения на `demo-wiki`.

Все credentials paths являются строками событий. Скрипт не пытается читать
реальные AWS/Azure/Docker файлы и не отправляет эти пути на чужие серверы.
Source credentials генерируются только внутри временной базы и не попадают
в изображения/manifest/Git.

Cloud sequence помещается в одно завершённое 5-минутное окно, чтобы finding
содержал все шесть путей независимо от минуты запуска. UI использует фиксированный
Date.now относительно базового времени набора; реальные даты генерации меняются.

Регенерация воспроизводит сценарий и смысл экранов, но не обещает побайтово
одинаковые PNG: меняются UTC timestamps, UUID, Git state и возможные шрифты/renderer.

## Manifest и проверка

[manifest.json](../images/manifest.json) содержит:

- `synthetic=true`, базовое и фактическое время съёмки;
- число событий и host ID временного набора;
- source commit и признак незакоммиченного дерева на момент съёмки;
- origin docs-стенда и desktop viewport;
- описание и SHA256 каждого PNG;
- явную отметку смоделированного API error.

`scripts/check_docs.py` проверяет локальные Markdown links, наличие изображений
и их checksums/PNG headers. Проверка ссылок не является полноценным Markdown
renderer и не заменяет просмотр изображений глазами.

## Как добавлять новую иллюстрацию

1. Используйте только документационные IP и безопасные поля.
2. Добавьте при необходимости небольшой fixture в documentation.json.
3. Измените [seed_documentation.py](../../scripts/seed_documentation.py), если нужен
   другой детерминированный временной сценарий.
4. В [capture_documentation.py](../../scripts/capture_documentation.py) дождитесь
   нужного экрана и ожидаемых данных, затем снимайте screenshot.
5. Явно подпишите любую подмену ответа/API state.
6. Обновите страницу вики, alt-текст и каталог изображений.
7. Запустите генерацию, проверку ссылок и визуально просмотрите результат.

Не ретушируйте рабочие IP поверх screenshot, надеясь скрыть все сведения:
безопаснее изначально снять синтетический стенд. Не подменяйте скриншот
AI-иллюстрацией или макетом несуществующей функции.

Использованные механизмы:
[Playwright screenshots](https://playwright.dev/python/docs/screenshots),
[Compose merge/override](https://docs.docker.com/reference/compose-file/merge/).

**К началу:** [Вики AttackScope](README.md).
