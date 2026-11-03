# Проверка первой публикации

## Состав

Публикация подготовлена из отслеживаемых исходников, а не копированием рабочего
каталога целиком. Включены приложение, lockfiles, тесты, конфигурации-примеры,
документация и синтетические UI screenshots. Прежняя локальная история не входит
в новую историю: в GitHub отправляется один начальный root commit.

Не включены локальные env, реальные журналы и БД, source credentials, private keys,
backups, образы, node_modules, runtime directories и отчёты о конкретном сервере.
Адреса и SSH identity конкретной установки удалены. Host/user для deploy обязательны;
VM примеры используют /srv/attackscope, vm.example.com и стандартные SSH параметры.
Разовые scripts обновления host и изменения чужого Nginx исключены.

Лицензия самого проекта пока не выбрана. LICENSE проекта не публикуется;
лицензии и notices сторонних компонентов сохранены.

## Метод проверки

- Проверка точного списка отслеживаемых файлов и изменений относительно исходников.
- Gitleaks v8.30.1 с default rules, --redact, без сети и без credential mounts.
- Дополнительный поиск реквизитов конкретной установки, credentials/ключей,
  IP-адресов, локальных абсолютных путей и неожиданных бинарных файлов.
- Изображения относятся к отдельному synthetic demo: provenance и SHA256
  в images/manifest.json; на снимках документационные IP, а не рабочие журналы.
- Проверка документации, Compose и релевантных тестов приложения.

Gitleaks image закреплён по digest в CI. scripts/check_publication.py проверяет
tracked file policy. Автоматическое сканирование не является доказательством
абсолютного отсутствия любых возможных секретов и не заменяет review новых файлов.

## Результаты

Локальные проверки подготовленного набора:

- Gitleaks directory scan: no leaks found, default rules без исключений.
- Backend: 143 pytest, Ruff/format и strict mypy — passed.
- Frontend: 16 Vitest, ESLint/Prettier/TypeScript/build — passed.
- Deployment failure-path tests: 7 — passed, SSH/Docker подменены.
- Дополнительный lint/format инструментов и примерных host helpers — passed.
- Production Vector smoke на синтетических stdin records: normalization,
  cursor, file-secret placeholders, redaction, limits и disk delivery — passed.
- Compose main/docs/production example configuration — passed, без запуска VM.
- 42 Markdown-файла, 187 локальных ссылок, 12 PNG SHA256 — passed.
- File policy: 218 tracked files — passed; отдельный negative check подтвердил
  отказ при tracked .env во временном репозитории.
- Дополнительный поиск private infrastructure markers — passed.
- PNG metadata: дополнительных полей нет; назначение и synthetic provenance
  изображений проверены. Runtime assets не заменялись изображениями с production.

Сборка оставляет предупреждение Vite о крупном JS chunk; оно не скрыто настройкой.
Прежние benchmark/browser отчёты не выдаются за новый прогон всей CI-цепочки.
GitHub Actions run оценивается отдельно после push; на момент этой локальной
приёмки он ещё не запускался. Deployment на реальную VM не входит в публикацию
и из CI автоматически не выполняется.

Перед push дополнительно проверяются единственный root commit, его Git-объекты
через Gitleaks git scan и отсутствие иных refs, которые могли бы передать старую
историю. Отправляется явно только main, без --all/--tags/--mirror и без force.
