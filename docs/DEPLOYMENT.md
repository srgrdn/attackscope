# Обновление frontend по SSH

Скрипт — пример frontend-only rollout для заранее подготовленной установки.
Он не устанавливает AttackScope на произвольный сервер и не обновляет backend,
collector, базу, credentials, SSH или firewall. Реальные реквизиты задаёт оператор.

## Условия

Linux, Python 3.9+, Git, Docker, OpenSSH; чистое Git-дерево, ключ в ssh-agent,
проверенный host key и заранее настроенный sudo для доверенного оператора.
Пример предполагает каталог `/srv/attackscope/production`. Сверьте этот каталог
в scripts/deploy.py, deploy/production/update_frontend.py и конфигурациях до запуска.
Не выдавайте широкие sudo permissions только ради работы примера.

```sh
./scripts/deploy production --component frontend --host vm.example.com --user operator --port 22 --identity ~/.ssh/id_ed25519
```

Адрес и имя пользователя обязательны; публичного production endpoint по умолчанию
нет. Команда ниже показывает help без подключения к серверу:

```sh
./scripts/deploy --help
python3 -m unittest discover -s tests -p test_frontend_deploy.py
```

## Проверки и переключение

1. Локальный lock, чистое дерево и фиксация SHA.
2. Deploy failure-path tests, frontend lint/format/types/tests/build без сети.
3. Сборка runtime image и отдельного Chromium image.
4. Передача образа через SSH, сверка checksum/image ID и резерва диска.
5. Remote lock, сохранение предыдущего env и образа.
6. Кандидат с отдельным Unix socket без host ports; Chromium-проверка Timeline.
7. Переключение только frontend image и повторная проверка в браузере.
8. Проверка неизменности backend/collector IDs и удаление кандидата.

Используются BatchMode, StrictHostKeyChecking и отключённое agent forwarding.
Ключи не монтируются в сборочные контейнеры. Возможен краткий перерыв UI.
Проверки браузера моделируют задержку и пустые ответы; события в БД не добавляются.

## Ошибка и восстановление

При сбое выполняется попытка возврата предыдущих env/image. Обрыв SSH, SIGKILL
или сбой rollback могут оставить lock. Сохраняйте ID транзакции и изучите state
перед повторным запуском. Не удаляйте чужой lock вслепую.

```sh
./scripts/deploy production --host vm.example.com --user operator --identity ~/.ssh/id_ed25519 --abort RELEASE_ID
```

Abort относится только к незавершённой транзакции с совпадающим owner lock.
Unit tests используют подмену Docker/SSH и не заменяют проверку аварийного
отката на вашей инфраструктуре. Скрипт не выполняет автоматический prune.

Для backend нужны отдельные backup, migration review и проверка совместимости
на копии БД. См. [OPERATIONS.md](OPERATIONS.md) и [PRODUCTION.md](PRODUCTION.md).
