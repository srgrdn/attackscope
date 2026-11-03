# Этап 3: Timeline MVP

Добавлены GET `/api/v1/timeline`, ECharts 6.1.0 и интерактивный главный экран.
Одинаковые фильтры с events: полуоткрытый UTC диапазон, host, IP, category,
source, destination port и severity. Ответ содержит до 1500 отдельных событий (этап 8 адаптирует порог к ширине экрана);
на плотном диапазоне возвращаются временные группы по source/category с точным
count. Размер интервала автоматически ограничивает ответ примерно 2004 группами.
SQL использует time/dimension indexes и query deadline. Сервер не пересылает
месячную таблицу событий в браузер. Агрегирование пока по retained detail;
исторические hourly rollups подключаются на этапе 8.

UI: 1h/24h/7d/30d, произвольные даты UTC, VM/IP/category/port, zoom/pan,
slider/wheel, карточка события и переход к IP (страница появится на этапе 6).
Наблюдения отображаются кружками; результаты классификации добавит этап 5.
Tooltip рисуется как richText на canvas; журнальные значения в карточках — React text.
Empty/loading/error обработаны. Обновление выбранного диапазона — polling 30 s;
кнопка пресета снова выбирает диапазон относительно текущего времени.

Проверки: 83 backend tests, Ruff, mypy; 7 frontend tests, lint/types/build;
Compose healthy, HTTP timeline возвращает корректный JSON. При ручном bind-mount
backend тест demo сначала упал из-за скрытого fixtures; с `/app/fixtures` проверка
повторена. Тесты включают 2000 событий → одна группа count=2000, границы
[from,to), IP filter, empty, а также XSS-строку в event detail.

Самостоятельно: `docker compose up --build --wait`, затем
`docker compose exec backend python -m attackscope.demo --run-name timeline-check`.
Открыть http://localhost:8180, выбрать 24h, нажать событие, изменить фильтры/масштаб.
Реальный браузер пока не автоматизирован; production build предупреждает о chunk
ECharts >500 kB (около 268 kB gzip). Проверка browser UX запланирована до release.

Документация API ECharts: https://echarts.apache.org/handbook/en/concepts/event/.
