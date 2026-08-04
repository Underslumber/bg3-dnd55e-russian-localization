---
name: release
description: "Подготавливает, публикует и проверяет релизы мода: версия и тег, changelog, commit/push gates, GitHub Actions, GitHub Release, Nexus Mods и mod.io. Активируй при запросах «выпусти релиз», «создай тег», «подготовь changelog», «опубликуй», «проверь релиз», «что с релизом» и release verification."
---

# Релиз

Выполняй релиз по проверяемым этапам. Не считай tag push доказательством успешной публикации.

## Сначала определи операцию

- Подготовка версии или changelog: работать локально, ничего не публиковать.
- Commit/push: выполнить только после явного подтверждения Gate A.
- Публикация релиза: создать и push-нуть tag только после явного подтверждения Gate B.
- Проверка существующего релиза: выполнять только read-only запросы к workflow/release API.
- Локальный запуск mod.io/Nexus-публикации: не выполнять без отдельного прямого запроса.

Если версия или канал не заданы и их нельзя однозначно вывести из текущего состояния, задай один вопрос на одно решение.

## Загрузи нужные ссылки

- Версия и tag: [references/versioning.md](references/versioning.md).
- Changelog: [references/changelog.md](references/changelog.md).
- CI, Nexus и mod.io: [references/publishing.md](references/publishing.md).
- Проверка готового релиза: [references/verification.md](references/verification.md).

Читай только относящиеся к текущей операции файлы. Для полного релиза прочитай все четыре.

## Полный workflow

1. Проверь ветку, `git status`, remotes и существующие tags. Не перезаписывай пользовательские изменения.
2. Определи tag и синхронизируй `ModuleInfo/Version64` по правилам versioning.
3. Составь changelog из реального diff относительно предыдущего релиза.
4. Запусти focused tests, `python scripts/validate-repo.py --mode pre-commit` и `git diff --check`.
5. Покажи пользователю tag, changelog, изменённые файлы и результаты проверок. Получи Gate A перед commit/push.
6. После Gate A повтори проверки, создай русский фактический commit и push-ни ветку. Не создавай tag.
7. На чистом опубликованном commit запусти `python scripts/validate-repo.py --mode pre-release --version-tag <tag>`.
8. Покажи окончательный changelog и получи отдельный Gate B перед созданием и push тега.
9. После Gate B создай tag на проверенном commit и push-ни его. Сразу выведи `[<tag>](<release-url>)`; поясни, что release может ещё собираться.
10. Жди и проверяй CI только если пользователь запросил публикацию до готового результата, мониторинг или проверку релиза. Следуй verification reference.

## Стоп-условия

- Версия не соответствует tag после `set-version.py` и повторной проверки.
- Worktree не чист перед tag.
- Проверки или тесты не прошли.
- Changelog не подготовлен.
- Нет явного подтверждения требуемого gate.
- Workflow успешен, но release или ожидаемый asset отсутствует.
- Имя или label asset отличается от контракта.

## Отчёт

- **done** — выполненный этап.
- **version** — tag и соответствующий `Version64`.
- **changelog** — пользовательские изменения.
- **checks** — локальные и удалённые проверки.
- **links** — workflow/release URL, если существуют.
- **remaining** — следующий gate или блокирующее условие.
