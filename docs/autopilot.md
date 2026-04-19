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

Workflow `.github/workflows/daily-translation-review.yml`:

- запускается раз в сутки в `18:00 UTC / 21:00 МСК` и вручную
- всегда выполняет Python-скрипты на актуальном дереве `main`
- пересобирает служебную review-ветку `autopilot/daily-translation-review` от текущего `main` перед коммитом результата
- хранит отдельное состояние upstream в `.github/autopilot/daily-review-state.json`
- обрабатывает только новые или изменённые записи, которых нет в `glossary/trusted-contentuid-versions.json`
- дополнительно проверяет итоговый `russian.xml` на неточности по глоссарию
- подготавливает точечные правки через OpenRouter и применяет их в review-ветке
- валидирует `russian.xml`
- пушит review-ветку и создаёт или обновляет draft PR в `main`

Если upstream не изменился, workflow завершится без расхода токенов.

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

В `daily-translation-review.yml` отправляется финальное сообщение со следующими полями:

- количество найденных ошибок перевода
- количество найденных неточностей перевода
- суммарная стоимость исправления
- ссылка на draft PR, где можно подтвердить слияние изменений

## Важно про запуск релиза

Если автопилот пушит commit/tag через стандартный `GITHUB_TOKEN`, GitHub не запускает следующий workflow на событие `push`.

Чтобы tag из `Autopilot Sync` реально запускал `.github/workflows/build.yml`, в environment `MedvedeBear - AI` нужен секрет:

- `AUTOPILOT_PUSH_TOKEN`

Это должен быть PAT или другой токен с правами на push в репозиторий.

## Как отключить автопилот

Установи `AUTOPILOT_MODE=off` или запусти workflow вручную с `mode_override=off`.

## Доверенный реестр

Файл `glossary/trusted-contentuid-versions.json` хранит проверенные пары `contentuid -> version`.

Он нужен, чтобы:

- не отправлять в LLM уже подтверждённые строки повторно;
- переводить только новые или реально изменённые записи;
- экономить токены в ежедневном review workflow.

Обновление реестра:

```powershell
python scripts/sync-trusted-contentuid-registry.py -RussianPath "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml" -RegistryPath glossary/trusted-contentuid-versions.json
```

Эта команда нужна, чтобы пересобрать доверенную базу из текущего подтверждённого `russian.xml`.

Проверка только новых или изменённых записей:

```powershell
python scripts/filter-trusted-contentuid-registry.py -RussianPath "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml" -RegistryPath glossary/trusted-contentuid-versions.json -OutputPath build/untrusted-contentuid-versions.json
```

Эта команда нужна, чтобы получить только те `contentuid/version`, которых ещё нет в доверенном реестре.
