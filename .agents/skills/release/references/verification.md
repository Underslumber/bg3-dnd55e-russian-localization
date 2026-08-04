# Проверка релиза

## Порядок

1. workflow status;
2. наличие GitHub Release;
3. наличие assets;
4. точное имя asset;
5. точный label asset.

Source of truth: GitHub workflow/release API, не локальный `build/`.

## Контракт asset

Для `<tag>`:

- local archive: `DnD 5.5e AIO Russian <tag>.zip`;
- GitHub asset name: `DnD.5.5e.AIO.Russian.<tag>.zip`;
- GitHub asset label: `DnD 5.5e AIO Russian <tag>.zip`.

## Команды

Используй `gh run list/view` для workflow и `gh release view <tag> --json url,assets` для release. Не считай страницу tag доказательством наличия release asset.

## Ожидание

- Один цикл ожидания: не более 30 секунд.
- Без отдельного запроса не ждать пассивно больше 120 секунд суммарно.
- После каждого цикла сообщать текущий этап и состояние.
- Более длительный мониторинг выполнять только по явному запросу пользователя.

## Остановка

- При несовпадении asset name или label остановиться и сообщить фактические значения.
- Если workflow успешен, а release/asset отсутствует, сообщить release URL, workflow URL и фактический asset list.
- После tag push сразу вывести предполагаемую ссылку release, но явно отметить, что готовность ещё не подтверждена.
