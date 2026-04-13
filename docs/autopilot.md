# Автопилот синхронизации перевода

## Что делает workflow

Workflow `.github/workflows/autopilot-sync.yml`:

- по расписанию и вручную скачивает upstream `english.xml`
- считает `sha256` содержимого
- сравнивает hash с `.github/autopilot/state.json`
- при изменениях запускает существующий pipeline обновления перевода
- валидирует `russian.xml`
- в режиме `sync_only` коммитит обновления
- в режиме `full` коммитит обновления и создаёт тег, после чего существующий `build.yml` сам выпускает релиз

Если hash не изменился и не включён `force_check` или `force_release`, workflow завершится без коммита, тега и Telegram-уведомлений.

## Требуемые environments

Workflow использует три GitHub environment:

- `AUTOPILOT_MODE` — переменные режима и git-автора
- `MedvedeBear - AI` — `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` и токен для push
- `TgBot` — Telegram secrets

## Требуемые secrets

- `OPENROUTER_API_KEY` — обязателен для автоперевода через OpenRouter
- `AUTOPILOT_PUSH_TOKEN` — обязателен для режима `full`, если tag должен запускать `.github/workflows/build.yml`
- `TG_BOT_TOKEN` — опционален, нужен для уведомлений Telegram
- `BOT_TOKEN` — опциональный fallback вместо `TG_BOT_TOKEN`
- `TG_CHAT_ID` — опционален, нужен для уведомлений Telegram
- `TG_THREAD_ID` — опционален, нужен для уведомлений Telegram

## Требуемые variables

- `AUTOPILOT_MODE` — `off`, `sync_only` или `full`
- `AUTOPILOT_GIT_AUTHOR_NAME` — имя автора для автокоммитов
- `AUTOPILOT_GIT_AUTHOR_EMAIL` — email автора для автокоммитов
- `AUTOPILOT_DEFAULT_RELEASE_CHANNEL` — опционально, `stable` или `prerelease`
- `OPENROUTER_MODEL` — модель OpenRouter для существующего translation pipeline

Если `AUTOPILOT_MODE` не задан, используется `off`.

## Режимы работы

- `off` — workflow только проверяет upstream и пишет summary
- `sync_only` — workflow обновляет перевод, валидирует XML и делает коммит
- `full` — workflow обновляет перевод, валидирует XML, делает коммит и создаёт тег

## Ручной запуск

Открой `Actions -> Autopilot Sync -> Run workflow` и укажи параметры:

- `mode_override`: `inherit`, `off`, `sync_only`, `full`
- `force_check`: принудительно пройти pipeline даже без нового hash
- `force_release`: разрешить выпуск тега в режиме `full` даже без новых правок
- `release_channel`: `stable` или `prerelease`
- `custom_tag`: собственный тег вместо авторасчёта
- `include_existing`: повторно переводить уже заполненные кандидаты
- `reason`: текстовая причина ручного запуска

## Telegram-уведомления

В новом workflow отправляются только два типа уведомлений:

- стартовое сообщение, только если upstream реально изменился или запуск принудительно переведён в обработку
- финальное сообщение со статусом, статистикой diff, количеством переведённых записей и стоимостью в `$`

Существующие уведомления релизной сборки в `.github/workflows/build.yml` не дублируются.

## Важно про запуск релиза

Если автопилот пушит commit/tag через стандартный `GITHUB_TOKEN`, GitHub не запускает следующий workflow на событие `push`.

Чтобы tag из `Autopilot Sync` реально запускал `.github/workflows/build.yml`, в environment `MedvedeBear - AI` нужен секрет:

- `AUTOPILOT_PUSH_TOKEN`

Это должен быть PAT или другой токен с правами на push в репозиторий.

## Как отключить автопилот

Установи `AUTOPILOT_MODE=off` или запусти workflow вручную с `mode_override=off`.
