---
name: translation-update
description: Агентское обновление русского перевода из апстрима: fetch upstream → compare → batched context → translate/review → apply. Активируй при запросах «обнови перевод», «translation update».
---

Ты выполняешь единый агентский workflow обновления перевода из апстрима.

`scripts/update-translation-openrouter.py` не используется: это отдельный OpenRouter pipeline, не часть этого навыка.

## Режимы

Аргументы: `$ARGUMENTS` (опционально: `incremental` или `full`)

- `incremental` — дополнить перевод изменениями из апстрима
- `full` — полный перевод с нуля

Если режим не передан:

1. Задай один вопрос host-native interactive tool.
2. Вопрос: какой режим использовать.
3. Варианты:
   - `Дополнение перевода изменениями из апстрима`
   - `Полный перевод с нуля`
4. После ответа не переспрашивай в рамках текущей сессии.

## Скрипты

- `.agents/skills/translation-update/scripts/get-upstream-english.py`
- `.agents/skills/translation-update/scripts/compare-translation.py`
- `.agents/skills/translation-update/scripts/prepare-translation-context.py`
- `.agents/skills/translation-update/scripts/apply-translation-edits.py`

## Входные данные

- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- `glossary/glossary.official.json` — первичный глоссарий (обязателен)
- `glossary/glossary.normalized.json` — вторичный глоссарий (только fallback)
- Апстрим EN: [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)

## Рабочая директория

Всегда работай через временную директорию в `%TEMP%`.

Пример структуры:

- `%TEMP%/bg3-translation-update-*/english.xml`
- `%TEMP%/bg3-translation-update-*/summary.json`
- `%TEMP%/bg3-translation-update-*/summary.md`
- `%TEMP%/bg3-translation-update-*/candidates.json`
- `%TEMP%/bg3-translation-update-*/working-russian.xml`

Никогда не оставляй в репозитории:

- `build/translation-diff/*`
- `.cache/upstream/english.xml`
- временные candidates/summary файлы

## Workflow

1. Создай временную рабочую директорию.
2. Скачай свежий upstream EN во временный `english.xml`:

```bash
python .agents/skills/translation-update/scripts/get-upstream-english.py --output-path "<temp>/english.xml" --force
```

3. Построй временный diff:

```bash
python .agents/skills/translation-update/scripts/compare-translation.py --english-path "<temp>/english.xml" --russian-path "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml" --output-dir "<temp>" --mode incremental
```

или для полного режима:

```bash
python .agents/skills/translation-update/scripts/compare-translation.py --english-path "<temp>/english.xml" --russian-path "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml" --output-dir "<temp>" --mode full
```

4. Прочитай `<temp>/summary.json`.
5. Если в `incremental` нет `addCount`, `updateCount` и `deleteCount` — сообщи «перевод актуален», удали временную директорию и остановись.
6. Если режим `incremental`:
   - создай `<temp>/working-russian.xml` как копию реального `russian.xml`
7. Если режим `full`:
   - создай `<temp>/working-russian.xml` как новый пустой XML:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<contentList>
</contentList>
```

8. Обрабатывай batched context через `prepare-translation-context.py`.
9. Сначала обработай `translate`, затем `review`.
10. После materialization итогового `<temp>/candidates.json` примени правки к `<temp>/working-russian.xml`.
11. Только после успешного apply+validation замени реальный `russian.xml`.
12. Удали временную директорию.

## Helper: batched context

Запуск:

```bash
python .agents/skills/translation-update/scripts/prepare-translation-context.py --candidates-path "<temp>/candidates.json" --official-glossary-path "glossary/glossary.official.json" --secondary-glossary-path "glossary/glossary.normalized.json" --kind translate --offset 0 --limit 25
```

Поддерживаемые `--kind`:

- `translate`
- `review`
- `all`

Helper печатает только один JSON object в `stdout`.

Поля результата:

- `mode`
- `kind`
- `stats`
- `hasMore`
- `nextOffset`
- `translateUnits[]`
- `reviewUnits[]`
- `deletes[]`
- `officialGlossary`
- `fallbackGlossary`

`stats.selectedEnglishTextChars` используй для контроля размера батча.

## Батчинг

- default batch: `limit = 25`
- дополнительный стоп-фактор: суммарный `englishText` в одном batched prompt не должен превышать `6000` символов
- если helper вернул больше текста, чем допустимо для prompt, сократи фактический batched prompt до подмножества первых units, укладывающихся в лимит
- `deletes[]` в LLM prompt не отправляй

## Контракт batched units

`translateUnits[]`:

- одна запись на уникальный `englishText`
- поля:
  - `unitId`
  - `englishText`
  - `targets[]`
- `targets[]` содержит:
  - `contentuid`
  - `version`
  - `section`

`reviewUnits[]`:

- одна запись на уникальную пару `englishText + currentRussianText`
- поля:
  - `unitId`
  - `englishText`
  - `currentRussianText`
  - `targets[]`

`deletes[]`:

- список `{contentuid}`

## Translate prompt contract

Для `translateUnits` проси агентский ответ только в JSON:

```json
{
  "translations": [
    {
      "unitId": "translate-00001",
      "text": "..."
    }
  ]
}
```

Правила:

- переводить на русский
- строго учитывать `officialGlossary`
- `fallbackGlossary` использовать только если нет official-правила
- сохранять placeholders, числа, XML/HTML/LSTag теги и переносы
- одинаковый `englishText` переводить один раз

## Review prompt contract

Для `reviewUnits` проси агентский ответ только в JSON:

```json
{
  "reviews": [
    {
      "unitId": "review-00001",
      "action": "keep_existing"
    },
    {
      "unitId": "review-00002",
      "action": "replace_text",
      "text": "..."
    }
  ]
}
```

Допустимые `action`:

- `keep_existing`
- `replace_text`

Смысл:

- `keep_existing` — английский текст можно обслужить обновлением `version` без изменения текущего RU текста
- `replace_text` — текущий RU текст нужно заменить новым переводом

## Materialization rules

Материализуй финальный `<temp>/candidates.json` так:

- `translateUnits`
  - для каждого `unitId` из `translations[]` запиши один и тот же `text` во все `targets`
  - это заполняет entries в `adds[]`
- `reviewUnits`
  - `keep_existing`
    - не добавляй поле `text` в соответствующие `updates[]`
    - оставь только `version` и служебные поля
  - `replace_text`
    - запиши новый `text` во все `targets` соответствующих `updates[]`
- `deletes[]`
  - оставь как есть

Никогда не оставляй незаполненные `adds[]`.

## Apply

Применяй итоговый temp candidates только к временному target XML:

```bash
python .agents/skills/translation-update/scripts/apply-translation-edits.py --russian-path "<temp>/working-russian.xml" --edits-path "<temp>/candidates.json"
```

После успешного apply:

1. замени содержимое `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml` содержимым `<temp>/working-russian.xml`
2. убедись, что в репозитории изменился только `russian.xml`

## Проверки

- `compare-translation.py` запускается только после успешной загрузки апстрима
- `prepare-translation-context.py` выводит только JSON в `stdout`
- `adds[]` всегда получают непустой `text`
- `review keep_existing` не записывает `text`
- `review replace_text` записывает непустой `text`
- `deletes[]` применяются вместе с остальными правками
- XML валиден после apply
- уникальность `contentuid` сохранена
- scope ограничен локализацией

## После успеха

Предложи выполнить skill `meta-sync` для синхронизации метаданных зависимостей из родительского мода.

## Формат отчёта

- **done** — что выполнено
- **changed_files** — изменённые файлы
- **checks** — результаты проверок
- **remaining** — что осталось (если есть)
