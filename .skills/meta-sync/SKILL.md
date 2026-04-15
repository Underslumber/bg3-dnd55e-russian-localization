---
name: meta-sync
description: Синхронизирует поля зависимостей (ModuleShortDesc) в meta.lsx из родительского мода. Активируй при запросах «обнови meta», «синхронизировать зависимости», «meta sync», «обновить версию зависимости».
---

Ты синхронизируешь поля зависимостей в `Mods/DnD 5.5e AIO Russian/meta.lsx` из родительского мода.

Прочитай и применяй: AGENTS.md, AGENT.common.md, AGENT.interaction.md.

Аргументы: $ARGUMENTS (опционально: URL родительского meta; по умолчанию — апстрим)

## Скрипт

`.skills/meta-sync/scripts/sync-parent-meta.py`

Запуск из корня репозитория:

```bash
python .skills/meta-sync/scripts/sync-parent-meta.py
# или с явным URL родительского meta:
python .skills/meta-sync/scripts/sync-parent-meta.py --parent-url <url>
```

## Входные данные

- URL родительского meta (опционально; по умолчанию — апстрим)
- `Mods/DnD 5.5e AIO Russian/meta.lsx`

## Порядок выполнения

1. Запусти `.skills/meta-sync/scripts/sync-parent-meta.py` (с аргументом из `$ARGUMENTS` если указан)
2. Убедись, что все обязательные поля родителя присутствуют: `Folder`, `MD5`, `Name`, `PublishHandle`, `UUID`, `Version64`; прерви если нет
3. Проверь что изменены только поля `ModuleShortDesc` в секции dependencies
4. Сообщи об изменённых полях

## Проверки

- XML валиден
- Все обязательные поля родительского мода присутствуют
- Изменены только поля `dependencies/ModuleShortDesc`

## Выходные файлы

- `Mods/DnD 5.5e AIO Russian/meta.lsx`

## Формат отчёта

- **done** — синхронизированные поля
- **changed_files** — изменённые файлы
- **checks** — результаты проверок
- **remaining** — что осталось (если есть)
