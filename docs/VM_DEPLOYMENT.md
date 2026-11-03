# Закрытое размещение на Linux VM

По умолчанию используйте [локальный quickstart](INSTALLATION.md).
Для VM предусмотрен overlay deploy/compose.vm.yaml с заранее собранными образами
и UI через Unix socket вместо host TCP ports. Это пример для оператора, а не
автоматический installer. Данные конкретного сервера в репозитории не хранятся.

## Подготовка

1. Создайте приватный каталог `/srv/attackscope` и подкаталог `run`.
2. Выберите владельца каталога и согласуйте численные UID/GID в vm.env.example.
3. Подготовьте образы нужного commit, проверьте digest и перенесите их на VM.
4. Создайте `.env` по deploy/vm.env.example; проверьте абсолютные пути и image tags.
5. Выполните `docker compose config --quiet` в подготовленном каталоге релиза.
6. Создайте backup существующих данных перед обновлениями и миграциями.
7. Запускайте подготовленную установку с `--no-build --pull never --wait`.

Пример env указывает COMPOSE_FILE; он должен выбирать основной Compose и overlay.
Overlay публикует UI через `/run/attackscope/ui.sock` внутри контейнера.
Приватный host-каталог socket должен быть доступен только доверенному оператору.
Сверьте bind mounts и владельцев до запуска. Не используйте общедоступный каталог
для socket и не открывайте UI в Интернет: multi-user login отсутствует.

## Подключение браузера

Пример с вымышленным hostname и стандартным SSH-путём:

```sh
ssh -a -i ~/.ssh/id_ed25519 -p 22 -N -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -L 127.0.0.1:18180:/srv/attackscope/run/ui.sock operator@vm.example.com
```

Откройте http://localhost:18180. Укажите свой проверенный hostname, user, port,
identity и фактический socket. `localhost` относится к компьютеру с браузером.
SSH key/passphrase не должны попадать в Git или в чат.

## Проверка и эксплуатация

Проверьте readiness, Timeline, фактический образ, отсутствие публичных host ports,
read-only filesystem, non-root users и сохранность volume. Перезапуск должен
сохранять данные; не используйте удаление volumes как способ исправления ошибок.
Наличие примерного файла не означает, что сбор реальных событий включён.

Для Vector и обслуживания: [PRODUCTION.md](PRODUCTION.md).
Для обновления frontend: [DEPLOYMENT.md](DEPLOYMENT.md).
Для backup/restore: [OPERATIONS.md](OPERATIONS.md).
