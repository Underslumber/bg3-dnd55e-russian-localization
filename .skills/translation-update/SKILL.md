---
name: translation-update
description: Полный цикл синхронизации русского перевода с апстримом: fetch upstream → compare → generate candidates → apply. Активируй при запросах «обнови перевод», «синхронизировать с апстримом», «translation update», «что нового в переводе».
---

Ты выполняешь полный цикл синхронизации перевода с апстримом.

Прочитай и применяй: AGENTS.md, AGENT.common.md, AGENT.interaction.md.

## Входные данные

- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- `glossary/glossary.official.json` — первичный глоссарий (обязателен)
- `glossary/glossary.normalized.json` — вторичный глоссарий (только запасной)
- Апстрим EN: [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)

## Порядок выполнения

1. Запусти `python scripts/get-upstream-english.py`; дождись `.cache/upstream/english.xml`
2. Запусти `python scripts/compare-translation.py` только после завершения шага 1
3. Прочитай `build/translation-diff/summary.json`:
   - Если нет `missing`, `version_mismatch` и `stale` — сообщи «перевод актуален» и остановись
   - Если diff есть — останови выполнение после генерации `build/translation-diff/candidates.json`; жди заполненных текстов от пользователя
4. После получения заполненных candidates:
   - Убедись, что ни один entry не имеет пустой `text`; прерви если есть
   - Используй `glossary/glossary.official.json` в первую очередь для согласованности терминов
   - `glossary/glossary.normalized.json` — только как запасной, без переопределения официальных терминов
5. Запусти skill `translation-tools` (операция `apply`) с заполненными candidates

## Проверки

- XML валиден после apply
- Термины согласованы с `glossary/glossary.official.json`
- Scope ограничен локализацией и разрешёнными метаданными
- Нет race condition между загрузкой апстрима и compare

## Выходные файлы

- `build/translation-diff/summary.json`
- `build/translation-diff/summary.md`
- `build/translation-diff/candidates.json`
- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`

## После успеха

Предложи выполнить skill `meta-sync` для синхронизации метаданных зависимостей из родительского мода.

## Формат отчёта

- **done** — что выполнено
- **changed_files** — изменённые файлы
- **checks** — результаты проверок
- **remaining** — что осталось (если есть)
