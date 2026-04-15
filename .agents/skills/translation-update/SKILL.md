---
name: translation-update
description: Ручное обновление русского перевода из апстрима: fetch upstream → compare → подготовка candidates → apply. Активируй при запросах «обнови перевод», «translation update».
---

Ты выполняешь единый ручной workflow обновления перевода из апстрима.

Аргументы: `$ARGUMENTS` (опционально: `diff` или `apply`; по умолчанию — `diff`)

## Скрипты

`.agents/skills/translation-update/scripts/get-upstream-english.py`

`.agents/skills/translation-update/scripts/compare-translation.py`

`.agents/skills/translation-update/scripts/apply-translation-edits.py`

Запуск из корня репозитория:

```bash
python .agents/skills/translation-update/scripts/get-upstream-english.py
python .agents/skills/translation-update/scripts/compare-translation.py
python .agents/skills/translation-update/scripts/apply-translation-edits.py --edits-path build/translation-diff/candidates.json
```

Если аргумент не указан — выполни `diff`.

## Входные данные

- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- `glossary/glossary.official.json` — первичный глоссарий (обязателен)
- `glossary/glossary.normalized.json` — вторичный глоссарий (только запасной)
- Апстрим EN: [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)

## Режим `diff`

1. Запусти `python .agents/skills/translation-update/scripts/get-upstream-english.py`; дождись `.cache/upstream/english.xml`
2. Запусти `python .agents/skills/translation-update/scripts/compare-translation.py` только после завершения шага 1
3. Прочитай `build/translation-diff/summary.json`:
   - Если нет `missing`, `version_mismatch` и `stale` — сообщи «перевод актуален» и остановись
   - Если diff есть — останови выполнение после генерации `build/translation-diff/candidates.json`; жди заполненных текстов от пользователя

## Режим `apply`

1. Убедись, что `build/translation-diff/candidates.json` существует и заполнен
2. Проверь, что ни один entry в `updates` и `adds` не имеет пустой `text`; прерви если есть
3. Используй `glossary/glossary.official.json` как основной терминологический источник при проверке готовых текстов
4. Используй `glossary/glossary.normalized.json` только как запасной, не переопределяя официальный глоссарий
5. Запусти `python .agents/skills/translation-update/scripts/apply-translation-edits.py --edits-path build/translation-diff/candidates.json`
6. Сообщи об изменённых entries

## Проверки

- `compare-translation.py` запускается только после успешной загрузки апстрима
- `candidates.json` содержит только непустые `text` перед apply
- XML валиден после apply
- Уникальность `contentuid` сохранена
- Термины согласованы с `glossary/glossary.official.json`
- Scope ограничен локализацией и разрешёнными метаданными

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
