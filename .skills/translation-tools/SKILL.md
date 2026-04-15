---
name: translation-tools
description: Примитивы перевода: diff (fetch upstream + compare с russian.xml) и apply (применить заполненные candidates к russian.xml). Активируй при запросах «получить diff», «сравнить с апстримом», «применить candidates», «translation diff», «translation apply».
---

Ты выполняешь отдельную операцию над переводом: `diff` или `apply`.

Прочитай и применяй: AGENTS.md, AGENT.common.md, AGENT.interaction.md.

Аргументы: $ARGUMENTS

Если аргумент не указан — спроси пользователя:

```
Выбери операцию:

1) diff — получить апстрим и сравнить с russian.xml
2) apply — применить заполненные candidates к russian.xml
```

---

## diff

Получить upstream english.xml и сравнить с russian.xml.

### Порядок выполнения

1. Запусти `python scripts/get-upstream-english.py`; дождись `.cache/upstream/english.xml`
2. Запусти `python scripts/compare-translation.py` только после завершения шага 1
3. Прочитай `build/translation-diff/summary.json`; классифицируй расхождения: missing / changed / stale

### Проверки

- `.cache/` присутствует в `.gitignore`
- `compare-translation.py` запускается только после завершения `get-upstream-english.py`
- XML апстрима получен без ошибок

### Выходные файлы

- `.cache/upstream/english.xml`
- `build/translation-diff/summary.json`
- `build/translation-diff/summary.md`
- `build/translation-diff/candidates.json`

---

## apply

Применить заполненные candidates к russian.xml.

### Порядок выполнения

1. Создай временную копию `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
2. Загрузи `build/translation-diff/candidates.json`; прерви если любой entry имеет пустой `text`
3. Примени updates и новые entries по `contentuid`
4. Запиши результат как UTF-8 BOM XML во временную копию
5. Запусти `python scripts/validate-translation-xml.py --xml-path "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml"`
6. Замени оригинальный `russian.xml` только после успешной валидации
7. Сообщи об изменённых entries

### Проверки

- XML валиден
- Уникальность `contentuid` сохранена
- Изменены только запрошенные entries
- Нет частичной замены при ошибке валидации

### Выходные файлы

- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`

---

## Формат отчёта

- **done** — выполненная операция
- **changed_files** — изменённые файлы
- **checks** — результаты проверок
- **remaining** — что осталось (если есть)
